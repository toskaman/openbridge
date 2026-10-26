#requires -Version 7.0
param(
    [Parameter(Mandatory=$true)][string]$ObservedAt,
    [Parameter(Mandatory=$true)][double]$FreeCredits,
    [Parameter(Mandatory=$true)][string]$ObservationId
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$observed=[DateTimeOffset]::Parse($ObservedAt)
$age=([DateTimeOffset]::UtcNow-$observed).TotalSeconds
if ($age -lt 0 -or $age -gt 300) { throw 'Credit observation expired. No credential loaded or provider called.' }
$secretPath=Join-Path $env:LOCALAPPDATA 'OpenBridge/meta-key.xml'
if (-not (Test-Path -LiteralPath $secretPath)) { throw 'User-encrypted Meta credential unavailable.' }
$secret=Import-Clixml -LiteralPath $secretPath
$startInfo=[Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName=(Get-Command python).Source
$startInfo.WorkingDirectory=$root
$startInfo.UseShellExecute=$false
$startInfo.CreateNoWindow=$true
$startInfo.RedirectStandardInput=$true
$startInfo.RedirectStandardOutput=$true
$startInfo.RedirectStandardError=$true
foreach ($argument in @('-m','dev.runtime_smoke','--observed-at',$ObservedAt,'--free-credits',$FreeCredits.ToString([Globalization.CultureInfo]::InvariantCulture),'--observation-id',$ObservationId)) { $startInfo.ArgumentList.Add($argument) }
$child=[Diagnostics.Process]::new()
$child.StartInfo=$startInfo
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $child.Start() | Out-Null
    $child.StandardInput.WriteLine([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
    $child.StandardInput.Close()
} finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
$output=$child.StandardOutput.ReadToEnd()
$errors=$child.StandardError.ReadToEnd()
$child.WaitForExit()
if ($child.ExitCode -ne 0) { Write-Output $output; throw 'Supervised runtime verification blocked or failed; no automatic retry.' }
$receipt=$output | ConvertFrom-Json
if ($receipt.model_id -ne 'muse-spark-1.3') { throw 'Unexpected model identity; receipt not published.' }
$receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $root 'docs/runtime-meta-receipt.json')
Write-Output 'Supervised runtime request succeeded. Sanitized receipt saved to docs/runtime-meta-receipt.json.'
Write-Output ('Estimated cost USD: '+$receipt.estimated_cost_usd)
$child.Dispose()
