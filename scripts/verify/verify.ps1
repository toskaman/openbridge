$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python -m compileall -q src tests
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
Write-Host 'Unit, integration and compilation checks passed.'
