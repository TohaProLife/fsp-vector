$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'local_processes.ps1')
$Record = Get-Content -LiteralPath (Join-Path $WorkspaceRoot '.local/processes.json') -Raw | ConvertFrom-Json
$RuntimeRecords = @()
foreach ($Entry in @(@{path='.local/pgdata/postmaster.pid';kind='postgres'},
    @{path='.local/keycloak.pid';kind='keycloak'}, @{path='.local/mailpit.pid';kind='mailpit'})) {
    $PathValue = Join-Path $WorkspaceRoot $Entry.path
    if (Test-Path -LiteralPath $PathValue) {
        $ParsedId = 0
        if ([int]::TryParse((Get-Content -LiteralPath $PathValue -TotalCount 1), [ref]$ParsedId)) {
            $RuntimeRecords += @{id=$ParsedId;kind=$Entry.kind}
        }
    }
}
$Inventory = @(Get-CimInstance Win32_Process)
$Selected = @(Select-VectorProcesses $Record $Inventory $WorkspaceRoot $RuntimeRecords -IncludeRuntime -ExcludedIds @($PID))
$Measured = @(); $CpuBefore = @{}
foreach ($Identity in $Selected) {
    $ProcessValue = Get-Process -Id ([int]$Identity.ProcessId) -ErrorAction SilentlyContinue
    if (-not $ProcessValue) { continue }
    try {
        if (-not (Test-VectorHandleBirth $Identity $ProcessValue)) { continue }
        $CpuBefore[[int]$Identity.ProcessId] = @{identity=$Identity;cpu=$ProcessValue.TotalProcessorTime.TotalSeconds}
        $Measured += [ordered]@{process=$ProcessValue.ProcessName;
            working_set_mb=[math]::Round($ProcessValue.WorkingSet64 / 1MB, 2);
            private_mb=[math]::Round($ProcessValue.PrivateMemorySize64 / 1MB, 2)}
    } catch { continue } finally { $ProcessValue.Dispose() }
}
$SampleClock = [Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Seconds 2
$CpuSeconds = 0.0
$AfterById = @{}
foreach ($Entry in @(Get-CimInstance Win32_Process)) { $AfterById[[int]$Entry.ProcessId] = $Entry }
foreach ($IdValue in $CpuBefore.Keys) {
    $Current = $AfterById[$IdValue]
    if (-not (Test-VectorProcessIdentity $CpuBefore[$IdValue].identity $Current)) { continue }
    $ProcessValue = Get-Process -Id $IdValue -ErrorAction SilentlyContinue
    if (-not $ProcessValue) { continue }
    try {
        if (-not (Test-VectorHandleBirth $Current $ProcessValue)) { continue }
        $CpuSeconds += [math]::Max(0, $ProcessValue.TotalProcessorTime.TotalSeconds - $CpuBefore[$IdValue].cpu)
    } catch { continue } finally { $ProcessValue.Dispose() }
}
$SampleClock.Stop()
$Computer = Get-CimInstance Win32_ComputerSystem
$Processor = Get-CimInstance Win32_Processor | Select-Object -First 1
$WorkingSetSum = 0.0
foreach ($Entry in $Measured) { $WorkingSetSum += $Entry['working_set_mb'] }
$Report = [ordered]@{
    status='measured'; measured_at=[DateTime]::UtcNow.ToString('o'); os='Windows';
    physical_ram_gb=[math]::Round($Computer.TotalPhysicalMemory / 1GB, 2);
    processors=[Environment]::ProcessorCount; processes=$Measured; cpu_model=$Processor.Name;
    sampled_idle_cpu_percent=[math]::Round(100 * $CpuSeconds / $SampleClock.Elapsed.TotalSeconds / [Environment]::ProcessorCount, 2);
    cpu_sample_seconds=[math]::Round($SampleClock.Elapsed.TotalSeconds, 3);
    startup_seconds=$Record.startup_seconds; startup_scope=$Record.startup_scope;
    working_set_sum_mb=[math]::Round($WorkingSetSum, 2);
    limitations=@('Instant process memory snapshot; shared pages may be counted more than once.',
        'Two-second CPU sample at rest, not sustained load capacity.',
        'Startup excludes first installation, downloads and web build; existing runtimes may already be running.',
        'Validated application identities and provisioned runtime PID roots only; descendants must be born after their actual parent; audit shells excluded.')
}
$Report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $WorkspaceRoot 'docs/audits/resources.json') -Encoding utf8
$Report | ConvertTo-Json -Depth 6
