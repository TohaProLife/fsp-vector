param([switch]$Portable, [switch]$NoIdentity, [switch]$Production)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $runArgs = @('scripts/run_local.py')
    if ($Portable) { $runArgs += '--portable' }
    if ($NoIdentity) { $runArgs += '--no-identity' }
    if ($Production) { $runArgs += '--production-web' }
    & '.venv/Scripts/python.exe' @runArgs
} finally { Pop-Location }
