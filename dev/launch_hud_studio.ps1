<#
  Launch OpenBridge HUD Studio fully detached (WMI Win32_Process.Create): the process is not a child
  of the calling shell/bridge job, inherits no pipes, and survives the caller's timeout.
    powershell -NoProfile -ExecutionPolicy Bypass -File dev\launch_hud_studio.ps1 [-Model "ENGO 2"] [-View oled] [-NoAdb]
#>
param([string]$Model = "ENGO 2", [string]$View = "oled", [string]$Scale = "fit", [switch]$NoAdb, [string]$Device = "")
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
# stop previous studio / legacy emulator instances
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -match 'hud_studio|activelook_emulator' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "stopped pid $($_.ProcessId)" }
Start-Sleep -Milliseconds 600
if (-not $NoAdb) {
  $adbArgs = @(); if ($Device) { $adbArgs = @('-s', $Device) }
  & adb @adbArgs reverse tcp:7789 tcp:7789 2>&1 | Out-Null
  "adb reverse tcp:7789 -> exit $LASTEXITCODE"
}
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe).Source }
$log = Join-Path $root 'dev\hud_studio.log'
$argsList = @('-u', '-m', 'src.adapters.hud_studio', '--model', "`"$Model`"", '--view', $View, '--scale', "$Scale", '--log', "`"$log`"")
# ShellExecute launch (no redirection) => no inherited pipe handles: the caller can exit immediately.
$p = Start-Process -FilePath $py -ArgumentList $argsList -WorkingDirectory $root -WindowStyle Maximized -PassThru
"launched pid $($p.Id) ($py) -> log $log"
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 250
  if (Get-NetTCPConnection -LocalPort 7790 -State Listen -ErrorAction SilentlyContinue) { "control API up on 127.0.0.1:7790"; break }
}
