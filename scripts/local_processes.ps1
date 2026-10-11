param([ValidateSet('Capture', 'StopRoot')][string]$Mode = 'Capture')

# Shared, fail-closed process selection. Functions accept CIM-shaped objects so
# tests can exercise PID reuse without enumerating or stopping live processes.
function Get-VectorBirth($Entry) {
    if ($null -eq $Entry -or $null -eq $Entry.CreationDate) { return $null }
    try { return ([DateTimeOffset]$Entry.CreationDate).UtcDateTime } catch { return $null }
}

function Test-VectorWorkspaceCommand($Entry, [string]$WorkspaceRoot) {
    if (-not $Entry.CommandLine) { return $false }
    $Command = ([string]$Entry.CommandLine).Replace('/', '\').ToLowerInvariant()
    $Prefix = [IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd('\').ToLowerInvariant() + '\'
    return $Command.Contains($Prefix)
}

function Test-VectorApplicationRoot($Entry, [string]$WorkspaceRoot, [switch]$Supervisor) {
    if (-not (Get-VectorBirth $Entry) -or -not $Entry.ExecutablePath -or
        -not (Test-VectorWorkspaceCommand $Entry $WorkspaceRoot)) { return $false }
    $Command = ([string]$Entry.CommandLine).Replace('/', '\')
    if ($Supervisor) {
        return $Entry.Name -ieq 'python.exe' -and $Command -match '(?i)(?:^|["\s\\])scripts\\run_local\.py(?:["\s]|$)'
    }
    if ($Entry.Name -ieq 'node.exe') {
        return $Command -match '(?i)\\apps\\web\\node_modules\\next\\dist\\bin\\next(?:["\s]|$)'
    }
    return $Entry.Name -ieq 'python.exe' -and
        ($Command -match '(?i)-m\s+app\.worker(?:\s|$)' -or
         ($Command -match '(?i)-m\s+uvicorn\s+' -and
          $Command -match '(?:app\.main:app|services\.integrations\.receiver:app)(?:\s|$)'))
}

function Test-VectorRuntimeProcess($Entry, [string]$WorkspaceRoot) {
    $Runtime = [IO.Path]::GetFullPath((Join-Path $WorkspaceRoot '.runtime')).TrimEnd('\') + '\'
    $Exe = ([string]$Entry.ExecutablePath).Replace('/', '\')
    $Command = ([string]$Entry.CommandLine).Replace('/', '\')
    return ($Entry.Name -in @('postgres.exe', 'java.exe', 'mailpit.exe') -and
        $Exe.StartsWith($Runtime, [StringComparison]::OrdinalIgnoreCase)) -or
        ($Entry.Name -ieq 'cmd.exe' -and $Command -match '(?i)\\keycloak-[^\\]+\\bin\\kc\.bat' -and
         $Command.IndexOf($Runtime, [StringComparison]::OrdinalIgnoreCase) -ge 0)
}

function Test-VectorRuntimeRoot($Entry, $RuntimeRecord, [string]$WorkspaceRoot) {
    if (-not (Get-VectorBirth $Entry) -or -not (Test-VectorRuntimeProcess $Entry $WorkspaceRoot)) { return $false }
    $Command = ([string]$Entry.CommandLine).Replace('/', '\')
    switch ($RuntimeRecord.kind) {
        'postgres' { return $Entry.Name -ieq 'postgres.exe' -and
            $Command.IndexOf((Join-Path $WorkspaceRoot '.local\pgdata'), [StringComparison]::OrdinalIgnoreCase) -ge 0 }
        'mailpit' { return $Entry.Name -ieq 'mailpit.exe' -and
            $Command.IndexOf((Join-Path $WorkspaceRoot '.local\mailpit.db'), [StringComparison]::OrdinalIgnoreCase) -ge 0 }
        'keycloak' { return $Entry.Name -in @('cmd.exe', 'java.exe') -and
            $Command -match '(?i)(?:\\keycloak-[^\\]+\\|start-dev)' }
        default { return $false }
    }
}

function Test-VectorProcessIdentity($Expected, $Current) {
    $Birth = Get-VectorBirth $Expected
    return $null -ne $Birth -and $null -ne $Current -and [int]$Expected.ProcessId -gt 4 -and
        [int]$Expected.ProcessId -eq [int]$Current.ProcessId -and $Birth -eq (Get-VectorBirth $Current) -and
        [int]$Expected.ParentProcessId -eq [int]$Current.ParentProcessId -and
        $Expected.Name -ieq $Current.Name -and $Expected.ExecutablePath -and
        [string]$Expected.ExecutablePath -ieq [string]$Current.ExecutablePath -and
        $Expected.CommandLine -and [string]$Expected.CommandLine -ceq [string]$Current.CommandLine
}

function Test-VectorHandleBirth($Expected, $ProcessValue) {
    $Birth = Get-VectorBirth $Expected
    if (-not $Birth) { return $false }
    # Win32_Process exposes microseconds, while the retained process handle has
    # 100ns ticks. Compare that exact microsecond bucket, never a seconds window.
    $Ticks = $ProcessValue.StartTime.ToUniversalTime().Ticks
    return ($Ticks - ($Ticks % 10)) -eq $Birth.Ticks
}

function Get-VectorProcessGraph($Inventory, $Roots, [string]$WorkspaceRoot, [switch]$IncludeRuntime, $ExcludedIds = @()) {
    $ById = @{}; $Repeated = [Collections.Generic.HashSet[int]]::new()
    foreach ($Entry in $Inventory) {
        $IdValue = [int]$Entry.ProcessId
        if ($ById.ContainsKey($IdValue)) { [void]$Repeated.Add($IdValue) } else { $ById[$IdValue] = $Entry }
    }
    foreach ($IdValue in $Repeated) { $ById.Remove($IdValue) }
    $Excluded = [Collections.Generic.HashSet[int]]::new()
    foreach ($IdValue in @(0, 4) + @($ExcludedIds)) { [void]$Excluded.Add([int]$IdValue) }
    $Selected = @{}
    foreach ($RootEntry in $Roots) {
        $IdValue = [int]$RootEntry.ProcessId
        if ($Excluded.Contains($IdValue) -or -not $ById.ContainsKey($IdValue) -or
            -not (Test-VectorProcessIdentity $RootEntry $ById[$IdValue])) { continue }
        if (-not $IncludeRuntime -and (Test-VectorRuntimeProcess $RootEntry $WorkspaceRoot)) { continue }
        $Selected[$IdValue] = $RootEntry
    }
    do {
        $Changed = $false
        foreach ($Entry in $ById.Values) {
            $IdValue = [int]$Entry.ProcessId; $ParentValue = [int]$Entry.ParentProcessId
            if ($Selected.ContainsKey($IdValue) -or $Excluded.Contains($IdValue) -or
                -not $Selected.ContainsKey($ParentValue)) { continue }
            $Birth = Get-VectorBirth $Entry
            if (-not $Birth -or $Birth -lt (Get-VectorBirth $Selected[$ParentValue])) { continue }
            if ($Entry.Name -notin @('python.exe','node.exe','conhost.exe','cmd.exe','postgres.exe','java.exe','mailpit.exe')) { continue }
            if ($Entry.CommandLine -match '(?i)(?:-m\s+pytest|[\\/](?:benchmark_local|check_source_archive|smoke_local|resource_snapshot|audit_[^\\/\s]+)\.(?:py|ps1))') { continue }
            if (-not $IncludeRuntime -and (Test-VectorRuntimeProcess $Entry $WorkspaceRoot)) { continue }
            if (-not $Entry.ExecutablePath -or -not $Entry.CommandLine) { continue }
            $Selected[$IdValue] = $Entry; $Changed = $true
        }
    } while ($Changed)
    return @($Selected.Values)
}

function Select-VectorProcesses($Record, $Inventory, [string]$WorkspaceRoot, $RuntimeRecords = @(), [switch]$IncludeRuntime, $ExcludedIds = @()) {
    if ([IO.Path]::GetFullPath([string]$Record.workspace) -ine [IO.Path]::GetFullPath($WorkspaceRoot)) { throw 'Runtime workspace mismatch.' }
    $Roots = @()
    try {
        $Started = [DateTimeOffset]::FromUnixTimeMilliseconds([long]([double]$Record.started_at * 1000)).UtcDateTime
        $Ready = [DateTimeOffset]::FromUnixTimeMilliseconds([long]([double]$Record.ready_at * 1000)).UtcDateTime
    } catch { throw 'Runtime start identity is unavailable.' }
    if ($Ready -lt $Started -or [double]$Record.started_at -le 0) { throw 'Runtime start identity is invalid.' }
    foreach ($Entry in $Inventory) {
        $IsSupervisor = [int]$Entry.ProcessId -eq [int]$Record.supervisor
        if (-not $IsSupervisor -and @($Record.children) -notcontains [int]$Entry.ProcessId) { continue }
        $Birth = Get-VectorBirth $Entry
        if (-not $Birth -or $Birth -gt $Ready.AddSeconds(2) -or
            $Birth -lt $Started.AddSeconds($(if ($IsSupervisor) { -30 } else { -2 }))) { continue }
        if (-not (Test-VectorApplicationRoot $Entry $WorkspaceRoot -Supervisor:$IsSupervisor)) { continue }
        if (-not $IsSupervisor -and [int]$Record.supervisor -gt 4 -and
            [int]$Entry.ParentProcessId -ne [int]$Record.supervisor) { continue }
        if (-not $IsSupervisor) {
            $Parents = @($Inventory | Where-Object { [int]$_.ProcessId -eq [int]$Entry.ParentProcessId })
            if ($Parents.Count -gt 1 -or ($Parents.Count -eq 1 -and
                (-not (Get-VectorBirth $Parents[0]) -or $Birth -lt (Get-VectorBirth $Parents[0])))) { continue }
        }
        $Stored = @($Record.identities | Where-Object { [int]$_.ProcessId -eq [int]$Entry.ProcessId })
        if ($Stored.Count -gt 0 -and ($Stored.Count -ne 1 -or -not (Test-VectorProcessIdentity $Stored[0] $Entry))) { continue }
        $Roots += $Entry
    }
    if ($IncludeRuntime) {
        foreach ($RuntimeRecord in $RuntimeRecords) {
            foreach ($Entry in $Inventory | Where-Object { [int]$_.ProcessId -eq [int]$RuntimeRecord.id }) {
                if (Test-VectorRuntimeRoot $Entry $RuntimeRecord $WorkspaceRoot) { $Roots += $Entry }
            }
        }
    }
    return @(Get-VectorProcessGraph $Inventory $Roots $WorkspaceRoot -IncludeRuntime:$IncludeRuntime -ExcludedIds $ExcludedIds)
}

function Stop-VectorSelectedProcess($Expected) {
    $IdValue = [int]$Expected.ProcessId
    if ($IdValue -le 4) { return $false }
    $Current = Get-CimInstance Win32_Process -Filter "ProcessId = $IdValue" -ErrorAction SilentlyContinue
    if (-not (Test-VectorProcessIdentity $Expected $Current)) { return $false }
    $Live = Get-Process -Id $IdValue -ErrorAction SilentlyContinue
    if (-not $Live) { return $false }
    try {
        # Open and retain this process handle before the final birth check; never
        # issue a PID-only tree operation after a process can have been replaced.
        [void]$Live.SafeHandle
        if (-not (Test-VectorHandleBirth $Expected $Live)) { return $false }
        Stop-Process -InputObject $Live -Force -ErrorAction Stop
        return $Live.WaitForExit(1000)
    } catch { return $false } finally { $Live.Dispose() }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    [Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $Request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $Inventory = @(Get-CimInstance Win32_Process)
    if ($Mode -eq 'Capture') {
        $Entry = @($Inventory | Where-Object { [int]$_.ProcessId -eq [int]$Request.process_id })
        $Started = [DateTimeOffset]::FromUnixTimeMilliseconds([long]([double]$Request.started_at * 1000)).UtcDateTime
        if ($Entry.Count -ne 1 -or [int]$Entry[0].ProcessId -le 4 -or
            (Get-VectorBirth $Entry[0]) -lt $Started.AddSeconds(-2) -or
            -not (Test-VectorApplicationRoot $Entry[0] $Request.workspace -Supervisor:([bool]$Request.supervisor))) {
            throw 'Own process identity could not be captured safely.'
        }
        @{ProcessId=[int]$Entry[0].ProcessId; ParentProcessId=[int]$Entry[0].ParentProcessId;
          Name=$Entry[0].Name; CreationDate=(Get-VectorBirth $Entry[0]).ToString('o');
          ExecutablePath=$Entry[0].ExecutablePath; CommandLine=$Entry[0].CommandLine} | ConvertTo-Json -Compress
    } else {
        if (-not (Test-VectorApplicationRoot $Request.identity $Request.workspace -Supervisor:([bool]$Request.supervisor))) {
            throw 'Application root identity is invalid.'
        }
        $Selected = @(Get-VectorProcessGraph $Inventory @($Request.identity) $Request.workspace -ExcludedIds @($PID))
        # Stop root first, preventing a supervisor from entering an older cleanup.
        $Ordered = @($Selected | Where-Object { $_.ProcessId -eq $Request.identity.ProcessId }) +
            @($Selected | Where-Object { $_.ProcessId -ne $Request.identity.ProcessId } | Sort-Object CreationDate -Descending)
        $Count = 0
        foreach ($Entry in $Ordered) { if (Stop-VectorSelectedProcess $Entry) { $Count++ } }
        @{stopped_count=$Count} | ConvertTo-Json -Compress
    }
}
