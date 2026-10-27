#requires -Version 7.0
param(
 [Parameter(Mandatory=$true)][string]$ObservedAt,
 [Parameter(Mandatory=$true)][double]$FreeCredits,
 [Parameter(Mandatory=$true)][string]$ObservationId,
 [string]$Brief='dev/meta-web-redesign-brief.txt',
 [string]$Model='muse-wonder-1.0'
)
$ErrorActionPreference='Stop'
$age=([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($ObservedAt)).TotalSeconds
if($age -lt 0 -or $age -gt 300){throw 'Credit confirmation expired; credential not loaded.'}
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$secret=Import-Clixml -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenBridge/meta-key.xml')
$start=[Diagnostics.ProcessStartInfo]::new()
$start.FileName=(Get-Command python).Source;$start.WorkingDirectory=$root
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
foreach($arg in @('-m','dev.meta_website_design','--observed-at',$ObservedAt,'--free-credits',$FreeCredits.ToString([Globalization.CultureInfo]::InvariantCulture),'--observation-id',$ObservationId,'--brief',$Brief,'--model',$Model)){$start.ArgumentList.Add($arg)}
$child=[Diagnostics.Process]::new();$child.StartInfo=$start
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try{$child.Start()|Out-Null;$child.StandardInput.WriteLine([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer));$child.StandardInput.Close()}
finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
try{$errors=$child.StandardError.ReadToEndAsync();$output=$child.StandardOutput.ReadToEnd();$child.WaitForExit();$errors.GetAwaiter().GetResult()|Out-Null;Write-Output $output;if($child.ExitCode -ne 0){throw 'Design request did not produce an accepted result; no automatic retry.'}}
finally{$child.Dispose()}
