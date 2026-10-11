$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $WorkspaceRoot
try {
    & '.venv/Scripts/python.exe' scripts/export_contract.py
    if ($LASTEXITCODE -ne 0) { throw 'API export failed.' }
    Push-Location apps/web
    try {
        npm exec --yes --package=openapi-typescript@7.13.0 -- openapi-typescript ../../docs/api/openapi.json -o src/lib/api.generated.ts
        if ($LASTEXITCODE -ne 0) { throw 'API type generation failed.' }
    } finally { Pop-Location }
} finally { Pop-Location }
