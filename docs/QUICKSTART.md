# OpenBridge quickstart (first-time install)

Requirements: Windows or Linux, Python 3.14 (standard library only — no
third-party runtime packages). Optional: Android platform-tools (`adb`) for
Android devices, Ollama for local Meta models, `bleak` for PC Bluetooth.

```sh
git clone https://github.com/toskaman/openbridge.git
cd openbridge
python -m unittest discover -s tests          # controlled tests; no hardware needed
python -m src.server                          # loopback-only server, default port 18765
```

Then open `http://127.0.0.1:18765` in a browser.

## First session

1. Press **Discover my environment** (bounded, read-only look at your network).
2. Or stay offline: run `python -m src.cli judge demo` for the labeled demo.
3. Open a device sheet to see sources, capabilities, and statuses.
4. To connect a real device, follow the on-screen pairing steps for that device
   kind (ADB Wi-Fi for Android, signed pairing for the Companion app).
5. Ask OpenBridge a request (*Scan for bluetooth devices*), review the preview,
   approve, and read the receipt.

## Diagnostics

```sh
python -m src.cli doctor                       # environment + model diagnostics
python -m src.cli models test --provider local # local Meta model reachability
python -m src.cli test smoke                   # fast offline smoke
```

Missing models and missing permissions are reported as explicit diagnostics,
never as silent failures.

## Local Meta models (optional, free)

```sh
python -m dev.start_local_meta --pull-model   # Llama 3.2 3B on :11437
python -m dev.start_glimmer --pull-model      # optional Muse Glimmer 30B on :11438 (~18 GB)
python -m src.server --local-meta --glimmer --agent
```

Hosted Meta calls are always consent-gated and budget-capped; nothing is spent
without your explicit approval.

## Shutdown

Stop the server with Ctrl+C. It releases its port and leaves no orphan
process; temporary journals live outside your working state.
