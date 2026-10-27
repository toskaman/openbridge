# Anonymous clone and isolated replay

Recorded 27 October 2026 on the participant's existing Windows PC. This is a fresh clone and isolated Python environment, **not a separate machine**. The acquisition stage uses network access; the selected test stage performs no dependency installation and runs under the existing Python I/O guard. It is not an operating-system network sandbox.

Observed public commit: `715da9638ed6747ba202f2e5a41dfdb5be7eaeb7`. Anonymous clone succeeded with credential helper, askpass and interactive authentication disabled. No local source overlays were applied. Disposable path: `%TEMP%/openbridge-release-anonymous-2596e3866d0b44d1bce6278df3a91128`.

Fresh `python -m venv` used the locally installed Python; no packages were installed. `python -m unittest discover -s tests/forge -q` returned **70 tests run, OK (skipped=2)** in 10.165 seconds. Guard startup asserted `GUARD_READY`, patched DNS, and patched subprocess identity. No guard log was created: zero blocked attempts observed. The two skips are retained; this is not a claim that browser coverage or all application tests ran. No physical calls, model requests, discovery launchers, preflight, cloud calls, browser downloads or model downloads were requested.

## Repeat against an explicitly selected public commit

Run in PowerShell. Replace the revision only after that commit is publicly available. Use a unique disposable path; do not point these commands at an existing checkout. No deletion is required.

```powershell
$replayRevision = '715da9638ed6747ba202f2e5a41dfdb5be7eaeb7'
$replayRoot = Join-Path $env:TEMP ('openbridge-release-anonymous-'+[guid]::NewGuid().ToString('N'))
git -c credential.helper= -c core.askPass= -c credential.interactive=never clone --no-checkout https://github.com/toskaman/openbridge.git $replayRoot
if ($LASTEXITCODE) { throw 'Anonymous acquisition failed' }
git -C $replayRoot checkout --detach $replayRevision
if ($LASTEXITCODE) { throw 'Requested public revision unavailable' }
python -m venv (Join-Path $replayRoot '.release-venv')
if ($LASTEXITCODE) { throw 'Environment creation failed' }
New-Item -ItemType Directory -Path (Join-Path $replayRoot '.release-guard') | Out-Null
Copy-Item -LiteralPath (Join-Path $replayRoot 'dev\controlled_io_guard.py') -Destination (Join-Path $replayRoot '.release-guard\sitecustomize.py')
$replayPython = Join-Path $replayRoot '.release-venv\Scripts\python.exe'
$priorPythonPath = $env:PYTHONPATH
$priorGuardLog = $env:OPENBRIDGE_TEST_GUARD_LOG
try {
    $env:PYTHONPATH = (Join-Path $replayRoot '.release-guard')+';'+$replayRoot
    $env:OPENBRIDGE_TEST_GUARD_LOG = Join-Path $replayRoot '.release-guard\blocked.jsonl'
    Push-Location $replayRoot
    try {
        & $replayPython -c "import sys,socket,subprocess;g=sys.modules.get('sitecustomize');assert g.GUARD_READY;assert socket.getaddrinfo is g.getaddrinfo and subprocess.Popen is g.GuardedPopen; print('guard active')"
        if ($LASTEXITCODE) { throw 'Guard inactive' }
        & $replayPython -m unittest discover -s tests/forge -q
        if ($LASTEXITCODE) { throw 'Replay failed' }
        if (Test-Path -LiteralPath $env:OPENBRIDGE_TEST_GUARD_LOG) { throw 'Inspect blocked I/O log; replay is not clean' }
    } finally { Pop-Location }
} finally {
    $env:PYTHONPATH = $priorPythonPath
    $env:OPENBRIDGE_TEST_GUARD_LOG = $priorGuardLog
}
```

Guard scope: blocks non-loopback Python socket/DNS traffic, local Ollama ports 11434/11437/11438/11439, and ADB device subprocess commands (`adb version` allowed). Native subprocess network traffic and alternative model ports are not universally sandboxed. The selected suite is deliberately narrow. Wider tests require review for discovery/device effects and optional dependencies before execution.

Release readiness requires rerunning against the final published commit and recording interpreter version, commit, full output, skips, guard status and log. This record covers the public baseline above; it does not verify uncommitted release documents or future source changes. Browser replay is a separate optional stage requiring licensed downloaded browser binaries and pinned package acquisition; none was run here.

## Full committed-source replay: ec653af

A second, fresh anonymous clone acquired exact public commit `ec653af2225e47601510a87ba73acf27aab5ecc6` with credential helpers/askpass/interactive authentication disabled. No source overlays were applied. Fresh venv: Python 3.14.4. During acquisition, installed `requirements-dev.txt` pins plus `jsonschema==4.26.0`; exact resolved dependencies and command outputs are in [committed-replay-ec653af.json](committed-replay-ec653af.json). Dependency installation succeeded; pip reported an ignored cache-deserialization warning, not an installation failure.

**Results: 349 unit/integration tests passed, no skips; all 12 browser modules passed.** Modules: Forge workspace selection, agent portal, offline, guided, fabric, Forge base, runtime, revocation during plan, publication failure, model memory, injected simulation and expiry. Commands and per-module duration/output are preserved in the JSON receipt. These are controlled software/browser checks, not new physical-device or actual-model journeys.

The existing `controlled_io_guard.py` was copied as startup `sitecustomize.py` into a new guard directory. Its self-test confirmed active DNS/subprocess patch identities and deliberately blocked non-loopback DNS, the actual model port and an ADB device command. Those three expected self-test blocks have a separate log. **No blocked attempts occurred during the test commands.** Python guard limitations still apply: this is not a native-process/browser network capture or an OS egress sandbox.

Browser execution explicitly reused **existing** `C:/Users/TheBox/.cache/openbridge-playwright` binaries through `PLAYWRIGHT_BROWSERS_PATH`. No new browser binary was downloaded. Fresh source clone and venv do not make this a fresh browser acquisition or an independent machine; execution used the same participant PC. No current application/model processes were changed, and no actual device or model request was requested. Public-source verification covers ec653af source; this appended documentation and receipt are later evidence files, not part of that tested commit.

To repeat the fuller stage, use the clone/venv recipe above with revision ec653af, install dependencies before enabling the guard, set the explicit browser cache, and run each command listed in the JSON. Record optional dependency resolution and browser acquisition/cache provenance anew; do not assume every future environment resolves the same unpinned jsonschema transitive versions.
