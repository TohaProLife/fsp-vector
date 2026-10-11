"""Exercise Windows process selection on mock CIM records; never stop a process."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / 'scripts/local_processes.ps1'
pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows process identity policy')
WORKSPACE = r'C:\vector'
BIRTH = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)


def entry(pid, parent, name='python.exe', seconds=0, command=None, executable=None):
    return {'ProcessId': pid, 'ParentProcessId': parent, 'Name': name,
            'CreationDate': (BIRTH + timedelta(seconds=seconds)).isoformat(),
            'ExecutablePath': executable or r'C:\Python314\python.exe',
            'CommandLine': command or rf'"{WORKSPACE}\.venv\Scripts\python.exe" -m uvicorn app.main:app'}


def run_ps(body, payload):
    """Only dot-source definitions; all inventory/identity data comes from stdin."""
    path = str(HELPER).replace("'", "''")
    script = f"$ErrorActionPreference='Stop'; . '{path}'; $x=[Console]::In.ReadToEnd()|ConvertFrom-Json; " + body
    result = subprocess.run([shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive', '-Command', script],
        input=json.dumps(payload), text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.lstrip('\ufeff'))


@pytest.fixture
def graph():
    supervisor = entry(800, 999, command=rf'"{WORKSPACE}\.venv\Scripts\python.exe" -X utf8 scripts/run_local.py --production-web')
    api = entry(1110, 800, seconds=1)
    nested = entry(1111, 1110, seconds=2)
    node = entry(1200, 800, 'node.exe', 2,
        rf'node.exe "{WORKSPACE}\apps\web\node_modules\next\dist\bin\next" start', r'C:\Program Files\nodejs\node.exe')
    runtime = entry(2000, 800, 'postgres.exe', 3,
        rf'"{WORKSPACE}\.runtime\pgsql\bin\postgres.exe" -D "{WORKSPACE}\.local\pgdata"',
        rf'{WORKSPACE}\.runtime\pgsql\bin\postgres.exe')
    inventory = [supervisor, api, nested, node, runtime,
        entry(1112, 1111, 'conhost.exe', 3, 'conhost.exe 0x4', r'C:\Windows\System32\conhost.exe'),
        entry(1201, 1200, 'node.exe', 3, 'next-server', r'C:\Program Files\nodejs\node.exe'),
        entry(2001, 2000, 'postgres.exe', 4, 'postgres: checkpointer', runtime['ExecutablePath']),
        entry(624, 800, 'csrss.exe', -172800, 'csrss.exe', r'C:\Windows\System32\csrss.exe'),
        entry(700, 800, 'wininit.exe', -172800, 'wininit.exe', r'C:\Windows\System32\wininit.exe'),
        # Allowed executable name makes chronology, rather than a name blacklist,
        # the reason this reused-PPID child is rejected.
        entry(900, 800, seconds=-172800),
        entry(500, 700, 'services.exe', -172790, 'services.exe', r'C:\Windows\System32\services.exe'),
        entry(2300, 999, 'powershell.exe', 4, rf'audit source mentions {WORKSPACE}\.runtime', r'C:\Windows\System32\powershell.exe'),
        entry(2400, 800, seconds=4, command=rf'python.exe {WORKSPACE}\scripts\benchmark_local.py'),
        entry(2500, 800, 'pwsh.exe', 4, 'resource_snapshot.ps1', r'C:\Program Files\PowerShell\pwsh.exe'),
        entry(0, 800, seconds=4), entry(4, 800, seconds=4)]
    record = {'workspace': WORKSPACE, 'supervisor': 800, 'children': [1110, 1200],
              'started_at': BIRTH.timestamp() + .1, 'ready_at': BIRTH.timestamp() + 10,
              'identities': [supervisor, api, node]}
    return {'inventory': inventory, 'record': record, 'workspace': WORKSPACE,
            'runtime': [{'id': 2000, 'kind': 'postgres'}]}


@pytest.mark.parametrize('include_runtime', [False, True])
def test_process_graph_rejects_old_reused_pid_system_tree_and_audit_helpers(graph, include_runtime):
    graph['include_runtime'] = include_runtime
    selected = run_ps("$s=@(Select-VectorProcesses $x.record $x.inventory $x.workspace $x.runtime "
        "-IncludeRuntime:([bool]$x.include_runtime) -ExcludedIds @(2500)); "
        "@{ids=@($s.ProcessId|Sort-Object)}|ConvertTo-Json -Compress", graph)['ids']
    assert set(selected) == {800, 1110, 1111, 1112, 1200, 1201} | ({2000, 2001} if include_runtime else set())


def test_recorded_roots_fail_closed_for_changed_identity_workspace_or_start_window(graph):
    cases = []
    for changed in ['CommandLine', 'CreationDate', 'ExecutablePath', 'Name', 'workspace_prefix', 'stale_pid', 'born_before_parent']:
        case = deepcopy(graph)
        case['record']['supervisor'] = 0
        case['record']['children'] = [1110]
        api = next(item for item in case['inventory'] if item['ProcessId'] == 1110)
        api['ParentProcessId'] = 0
        case['record']['identities'] = [deepcopy(api)]
        if changed == 'born_before_parent':
            case['record']['supervisor'] = 800
            case['record']['identities'] = []
            case['inventory'] = [api, next(item for item in case['inventory'] if item['ProcessId'] == 800)]
            api['ParentProcessId'] = 800
            api['CreationDate'] = (BIRTH - timedelta(seconds=1)).isoformat()
            # Also invalidate the supervisor role so it cannot seed descendants.
            case['inventory'][1]['CommandLine'] = 'python.exe unrelated.py'
        elif changed == 'workspace_prefix':
            api['CommandLine'] = api['CommandLine'].replace(WORKSPACE, WORKSPACE + '-other')
            case['record']['identities'] = [deepcopy(api)]
        elif changed == 'stale_pid':
            api['CreationDate'] = (BIRTH + timedelta(seconds=200)).isoformat()
            case['record']['identities'] = [deepcopy(api)]
        elif changed == 'CommandLine':
            api['CommandLine'] += ' --different-instance'
        elif changed == 'CreationDate':
            api['CreationDate'] = (BIRTH + timedelta(seconds=2)).isoformat()
        elif changed == 'Name':
            api['Name'] = 'unrelated.exe'
        else:
            api['ExecutablePath'] = r'C:\other\python.exe'
        cases.append(case)
    results = run_ps("$counts=@(foreach($case in $x){ "
        "@(Select-VectorProcesses $case.record $case.inventory $case.workspace).Count }); "
        "@{counts=$counts}|ConvertTo-Json -Compress", cases)['counts']
    assert results == [0] * len(cases)


def test_duplicate_pid_missing_birth_and_repeated_graph_do_not_admit_ambiguous_children(graph):
    graph['inventory'].append(deepcopy(next(item for item in graph['inventory'] if item['ProcessId'] == 1110)))
    graph['inventory'].append(entry(2600, 800, seconds=4))
    graph['inventory'][-1]['CreationDate'] = None
    selected = run_ps("$s=@(Select-VectorProcesses $x.record $x.inventory $x.workspace); "
        "@{ids=@($s.ProcessId|Sort-Object)}|ConvertTo-Json -Compress", graph)['ids']
    assert set(selected) == {800, 1200, 1201}
    # A repeated edge/cycle cannot cause an unbounded traversal.
    loop = entry(1110, 1111, seconds=1)
    child = entry(1111, 1110, seconds=1)
    result = run_ps("$s=@(Get-VectorProcessGraph $x.inventory @($x.root) $x.workspace); "
        "@{ids=@($s.ProcessId|Sort-Object)}|ConvertTo-Json -Compress",
        {'inventory': [loop, child], 'root': loop, 'workspace': WORKSPACE})['ids']
    assert set(result) == {1110, 1111}


def test_final_identity_revalidation_rejects_reused_pid_and_every_changed_identity_field():
    expected = entry(1110, 800, seconds=1)
    alternatives = [deepcopy(expected)]
    for field, value in [('ProcessId', 1111), ('ParentProcessId', 999), ('CreationDate', (BIRTH + timedelta(seconds=2)).isoformat()),
                         ('Name', 'node.exe'), ('ExecutablePath', r'C:\other\python.exe'), ('CommandLine', 'unrelated'), ('CreationDate', None)]:
        changed = deepcopy(expected)
        changed[field] = value
        alternatives.append(changed)
    result = run_ps("@{valid=@(foreach($current in $x.alternatives){ "
        "Test-VectorProcessIdentity $x.expected $current })}|ConvertTo-Json -Compress",
        {'expected': expected, 'alternatives': alternatives})['valid']
    assert result == [True] + [False] * (len(alternatives) - 1)


def test_handle_birth_matches_only_same_cim_microsecond_bucket():
    expected = entry(1110, 800, seconds=1)
    result = run_ps("$birth=Get-VectorBirth $x; @{valid=@(foreach($ticks in @(0,6,9,10,10000000)){ "
        "Test-VectorHandleBirth $x ([pscustomobject]@{StartTime=$birth.AddTicks($ticks)}) })}|ConvertTo-Json -Compress", expected)['valid']
    assert result == [True, True, True, False, False]


def test_stop_function_revalidates_mock_identity_and_uses_retained_exact_process_object():
    # Every OS lookup and termination command is replaced with a pure fake. No
    # Get-CimInstance/Get-Process/Stop-Process cmdlet is executed by this test.
    expected = entry(1110, 800, seconds=1)
    body = """
        $script:Expected=$x; $script:Current=$x; $script:StopCalls=0;
        $script:Fake=[pscustomobject]@{SafeHandle=[object]::new();StartTime=(Get-VectorBirth $x).AddTicks(6)};
        $script:Fake|Add-Member -MemberType ScriptMethod -Name Dispose -Value {};
        $script:Fake|Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { return $true };
        function Get-CimInstance { param($ClassName,$Filter,$ErrorAction) return $script:Current }
        function Get-Process { param($Id,$ErrorAction) return $script:Fake }
        function Stop-Process { param($InputObject,[switch]$Force,$ErrorAction)
            if(-not [object]::ReferenceEquals($InputObject,$script:Fake)){throw 'Wrong process object'}
            $script:StopCalls++
        }
        $first=Stop-VectorSelectedProcess $script:Expected;
        $script:Current=$x|Select-Object *;
        $script:Current.CreationDate=(Get-VectorBirth $x).AddSeconds(1).ToString('o');
        $second=Stop-VectorSelectedProcess $script:Expected;
        @{first=$first;second=$second;calls=$script:StopCalls}|ConvertTo-Json -Compress
    """
    assert run_ps(body, expected) == {'first': True, 'second': False, 'calls': 1}
