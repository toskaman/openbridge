# OpenBridge troubleshooting

Start every diagnosis with the read-only checks; they never touch a device:

```sh
python -m src.cli doctor                       # environment + model diagnostics
python -m src.cli models test --provider local # local Meta model reachability
python -m src.cli test smoke                   # fast offline smoke
python -m src.runtime.preflight                # pinned packages, adb, models, storage
```

Use `python3` instead of `python` on Linux/macOS where needed.

## Server won't start: port in use

The server binds loopback-only on port 18765 by default. If the port is taken:

```sh
python -m src.server --port 18799
```

Then open `http://127.0.0.1:18799`. Stop the server with Ctrl+C; it releases
its port and leaves no orphan process.

## Wrong Python version

OpenBridge needs Python 3.12 or newer and is developed on 3.14.4 with the
standard library only. If `doctor` reports a mismatch, install a supported
Python and re-run. The clean-room check (`scripts/verify/clean_install_check.py`)
runs in an isolated venv with no third-party packages; any third-party import
at runtime is a bug — report which module failed.

## Offline demo blocked

```sh
python -m src.cli judge demo
```

`DEMO_COMPLETE` means all required checks passed. `DEMO_BLOCKED` names the
failing checks in its readiness counts (`n/m required checks passed`); fix
those checks and re-run. The demo needs no hardware, no models, and no
network. See [OFFLINE_DEMO.md](OFFLINE_DEMO.md).

## Local models unreachable

- Llama 3.2 3B must serve on `http://127.0.0.1:11437`, Glimmer 30B on
  `http://127.0.0.1:11438`. Start them with `python -m dev.start_local_meta`
  and `python -m dev.start_glimmer` (add `--pull-model` on first run).
- A digest mismatch means the installed model is not the pinned one; the
  broker refuses to treat it as the pinned model. Re-pull the exact pinned
  tag from `config/runtime_models.json`.
- Glimmer 30B needs about 14 GB of VRAM and host-specific tuning: full GPU
  offload can fail on pinned-CUDA-host allocation (pin fewer layers, e.g.
  `num_gpu=28`) and reasoning traces can exhaust the token budget (disable
  thinking for terse prompts). See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
- Missing models are always reported as explicit diagnostics, never as
  silent failures.

## Cloud calls blocked

Hosted Meta calls need all of: the key in the OS secret store as
`OPENBRIDGE_META_KEY` (never a CLI argument or a file), a spend cap via
`OPENBRIDGE_CLI_BUDGET_USD`, and per-call `--spend --consent SPEND-APPROVED`.
Without them the call is refused by design. Preflight with
`openbridge models test --provider meta-cloud`.

## Android / adb issues

- `adb` must be on PATH (Android platform-tools). Without it, Android/TV
  features are disabled with an explicit diagnostic.
- Pairing codes are single-use and expire; `relay-pair-confirm` allows 5
  guesses per pending pairing, then invalidates it — start a fresh pairing
  and read the new on-screen code. The Companion app must be open on screen.
- A Galaxy Watch that dozes drops wireless adb; dispatch then raises
  `Relay unreachable` with the relay marked offline (never a phantom success
  receipt). Wake the watch and re-issue the command once it is awake.
- Pair requests are rate-limited to 1 per 5 s — wait and retry.

## Companion app build

```sh
python -m dev.build_companion
```

Needs Android SDK build-tools 34 (`javac` → `d8` → `aapt2` → `zipalign` →
`apksigner`). The APK is a local build artifact (`artifacts/`, gitignored)
and is never bundled in the release zips; see the release's
`COMPANION_STATUS.md`. No third-party libraries are used.

## Bluetooth / Tuya optionals missing

- PC Bluetooth needs `bleak==3.0.2` (`pip install -r requirements-optional.txt`),
  or use an Android Companion relay instead — no PC adapter required.
- Tuya devices need `tinytuya==1.20.0` plus owner linking first
  (`python -m dev.tuya_link`). Unlinked devices are refused.

## Where state lives

Per-user state (journals, reservations) lives under `%LOCALAPPDATA%\OpenBridge`
on Windows or `~/.local/share/OpenBridge` elsewhere. Temporary journals live
outside working state. Nothing is written outside these directories without
an explicit owner action.

## Still stuck

Re-run `python -m src.cli doctor`, copy its output, and note the exact
command, OS, Python version (`python --version`), and which step of
[QUICKSTART.md](QUICKSTART.md) failed. Honest failure output (refusals,
`UNCERTAIN`, `DEMO_BLOCKED`) is evidence, not a crash — include it verbatim.
