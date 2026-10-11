$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'local_processes.ps1')
$StatePath = Join-Path $WorkspaceRoot '.local/processes.json'
if (-not (Test-Path -LiteralPath $StatePath)) { Write-Output 'No recorded application instance.'; exit 0 }
$StateText = Get-Content -LiteralPath $StatePath -Raw
$State = $StateText | ConvertFrom-Json
$Selected = @(Select-VectorProcesses $State @(Get-CimInstance Win32_Process) $WorkspaceRoot -ExcludedIds @($PID))
# Stop the supervisor first to prevent competing cleanup when its child exits.
# Each target is freshly revalidated; provisioned runtime branches are excluded.
$Ordered = @($Selected | Where-Object { $_.ProcessId -eq $State.supervisor }) +
    @($Selected | Where-Object { $_.ProcessId -ne $State.supervisor } | Sort-Object CreationDate -Descending)
$StoppedCount = 0
foreach ($Entry in $Ordered) { if (Stop-VectorSelectedProcess $Entry) { $StoppedCount++ } }
$RemainingById = @{}
foreach ($Entry in @(Get-CimInstance Win32_Process)) { $RemainingById[[int]$Entry.ProcessId] = $Entry }
$Remaining = @($Selected | Where-Object { Test-VectorProcessIdentity $_ $RemainingById[[int]$_.ProcessId] })
if ($Remaining.Count -gt 0) { throw 'Some validated application processes remain; the process record is preserved.' }
if ($StoppedCount -gt 0 -and (Test-Path -LiteralPath $StatePath) -and
    (Get-Content -LiteralPath $StatePath -Raw) -ceq $StateText) {
    Remove-Item -LiteralPath $StatePath
}
Write-Output "Stopped $StoppedCount validated application processes; project PostgreSQL, Mailpit and Keycloak are preserved."
