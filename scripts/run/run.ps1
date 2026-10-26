param([switch]$LocalMeta,[switch]$Glimmer,[switch]$Agent)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
$a=@('-m','src.server')
if ($LocalMeta) { $a+='--local-meta' }
if ($Glimmer) { $a+='--glimmer' }
if ($Agent) { $a+='--agent' }
python @a
exit $LASTEXITCODE
