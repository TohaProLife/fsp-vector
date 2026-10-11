param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$PriorPythonPath = $env:PYTHONPATH
$PriorPgAudit = $env:RUN_PG_AUDIT
Push-Location $WorkspaceRoot
try {
    $env:PYTHONPATH = "$WorkspaceRoot/services/api;$WorkspaceRoot"
    $env:RUN_PG_AUDIT = if ($Postgres) { '1' } else { '0' }
    & "$WorkspaceRoot/.venv/Scripts/python.exe" -m pytest services/api/tests tests/integration -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Domain verification failed.' }
    Push-Location apps/web
    try {
        npm run typecheck
        if ($LASTEXITCODE -ne 0) { throw 'Frontend typecheck failed.' }
        npm run test:routes
        if ($LASTEXITCODE -ne 0) { throw 'Frontend route validation failed.' }
    } finally { Pop-Location }
} finally {
    $env:RUN_PG_AUDIT = $PriorPgAudit
    $env:PYTHONPATH = $PriorPythonPath
    Pop-Location
}
