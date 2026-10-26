param([switch]$LocalMeta)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
if ($LocalMeta) { python -m src.server --local-meta } else { python -m src.server }
exit $LASTEXITCODE
