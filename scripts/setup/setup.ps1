$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
python -c "import sys; print(sys.version); assert sys.version_info >= (3,14), 'Python 3.14+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python check failed' }
Write-Host 'Ready. No third-party runtime dependencies to install.'
