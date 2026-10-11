"""Windows cleanup of our own captured process identities; no PID tree kills."""
import json
from pathlib import Path
import subprocess
import sys
import time

HELPER = Path(__file__).with_suffix('.ps1')


def _request(mode, payload):
    completed = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
         '-File', str(HELPER), '-Mode', mode], input=json.dumps(payload), text=True, encoding='utf-8',
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode:
        raise RuntimeError('Local process identity operation failed safely; no unvalidated process was stopped.')
    return json.loads(completed.stdout.lstrip('\ufeff'))


def capture_process(process_id, workspace, started_at, *, supervisor=False):
    if sys.platform != 'win32':
        return None
    return _request('Capture', {'process_id': process_id, 'workspace': str(Path(workspace).resolve()),
                              'started_at': started_at, 'supervisor': supervisor})


def spawn_owned(command, *, workspace, **kwargs):
    started_at = time.time()
    process = subprocess.Popen(command, **kwargs)
    try:
        process._vector_identity = capture_process(process.pid, workspace, started_at)
    except Exception:
        # Popen retains the exact child handle. This fallback stops only that
        # child and does not enumerate PID descendants or another application.
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        raise
    return process


def terminate_owned(process, workspace):
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        identity = getattr(process, '_vector_identity', None)
        if not identity:
            raise RuntimeError('Own process creation identity is unavailable; cleanup refused.')
        _request('StopRoot', {'identity': identity, 'workspace': str(Path(workspace).resolve())})
    else:
        process.terminate()
