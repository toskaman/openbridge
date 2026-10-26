$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
& (Join-Path $root 'scripts/verify/verify.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
Set-Location $root
New-Item -ItemType Directory -Force -Path 'dist' | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
git archive --format=zip --output="dist/openbridge-$stamp.zip" HEAD
if ($LASTEXITCODE -ne 0) { throw 'Archive failed; commit source first' }
Write-Host "Created dist/openbridge-$stamp.zip from committed source."
