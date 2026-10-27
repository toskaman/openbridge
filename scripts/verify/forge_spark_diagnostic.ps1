#requires -Version 7.0
param(
    [Parameter(Mandatory=$true)][string]$ObservedAt,
    [Parameter(Mandatory=$true)][double]$FreeCredits,
    [Parameter(Mandatory=$true)][string]$ObservationId
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$age=([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($ObservedAt)).TotalSeconds
if ($age -lt 0 -or $age -gt 300) { throw 'Credit observation expired; no credential loaded.' }
$outDir=Join-Path $root 'artifacts/spark-diagnostic'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$receiptPath=Join-Path $outDir ('attempt-'+[guid]::NewGuid().ToString()+'.json')
$secret=Import-Clixml -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenBridge/meta-key.xml')
$start=[Diagnostics.ProcessStartInfo]::new()
$start.FileName=(Get-Command python).Source
$start.WorkingDirectory=$root
$start.UseShellExecute=$false
$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true
$start.RedirectStandardOutput=$true
$start.RedirectStandardError=$true
foreach ($argument in @('-m','dev.forge_spark_diagnostic','--observed-at',$ObservedAt,'--free-credits',$FreeCredits.ToString([Globalization.CultureInfo]::InvariantCulture),'--observation-id',$ObservationId)) { $start.ArgumentList.Add($argument) }
$child=[Diagnostics.Process]::new()
$child.StartInfo=$start
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $child.Start() | Out-Null
    $child.StandardInput.WriteLine([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
    $child.StandardInput.Close()
} finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
try {
    $errorRead=$child.StandardError.ReadToEndAsync()
    $output=$child.StandardOutput.ReadToEnd()
    $child.WaitForExit()
    $errorRead.GetAwaiter().GetResult() | Out-Null
    $receipt=$output | ConvertFrom-Json
    $receipt | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $receiptPath -Encoding utf8NoBOM
    if ($child.ExitCode -ne 0) { throw 'Diagnostic failed; sanitized attempt retained; no automatic retry.' }
    if ($receipt.model_id -ne 'muse-spark-1.3') { throw 'Unexpected model identity.' }
    Write-Output ('Sanitized receipt: '+$receiptPath)
    Write-Output ('Estimated cost USD: '+$receipt.estimated_cost_usd)
} finally { $child.Dispose() }
