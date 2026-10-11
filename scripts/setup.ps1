$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.14 and add it to PATH.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 24 LTS and add it to PATH.' }
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { python -m venv .venv; if ($LASTEXITCODE) { throw 'venv setup failed' } }
    & '.venv/Scripts/python.exe' -m pip install -r 'deploy/requirements.lock'
    if ($LASTEXITCODE) { throw 'Locked Python dependencies failed' }
    & '.venv/Scripts/python.exe' -m pip install --no-deps -e 'services/api[test]'
    if ($LASTEXITCODE) { throw 'Python dependencies failed' }
    & '.venv/Scripts/python.exe' scripts/bootstrap_runtime.py
    if ($LASTEXITCODE) { throw 'Runtime download failed' }
    Push-Location 'apps/web'
    try { npm.cmd ci; if ($LASTEXITCODE) { throw 'Web dependencies failed' } } finally { Pop-Location }
    & '.venv/Scripts/python.exe' scripts/local_runtime.py
    if ($LASTEXITCODE) { throw 'PostgreSQL startup failed' }
    Write-Output 'Setup complete. Run: .\scripts\start.ps1'
} finally { Pop-Location }
