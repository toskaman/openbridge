# Local vs cloud acceptance matrix (Prompt30 #5) — 30 Oct 2026

Paired arms where possible. Cloud arm is BLOCKED: no `OPENBRIDGE_META_KEY`
in the environment and no current spend order (plumbing + preflight proven,
spend needs explicit `--spend --consent SPEND-APPROVED`).

## Environment
- PC: Windows 10, RTX 4060 Ti 16 GB, 32 GB RAM.
- Local: Llama 3.2 3B :11437 (digest verified, CPU), Glimmer 30B :11438
  (digest verified, GPU offload). Both started 30 Oct via dev/ scripts.
- Devices: BV9300 Pro USB (Android 13), Pixel 6 AVD emulator-5556
  (Android 14). Watch/TV/vacuum ONLINE since 30 Oct late (rows 22-26);
  ESP32 absent; no Linux node online.

## Results

| Test | Local Meta | Paid Meta | Device proof |
|---|---|---|---|
| Discover + understand | PASS (CLI discover, ADB-verified facts) | BLOCKED (no key) | phone + AVD |
| Multi-device orchestration | PASS (wf-p30-phone-avd2: 2 captures + montage, sha verified) | BLOCKED | phone + AVD |
| Watch → TV controls | OPEN (devices online since 30 Oct late; run pending) | BLOCKED | — |
| TV → ESP32 controls | BLOCKED (devices absent) | BLOCKED | — |
| Windows → Linux diag | BLOCKED (no Linux node online) | BLOCKED | — |
| Watch → vacuum | OPEN (devices online since 30 Oct late; run pending) | BLOCKED | — |
| Unknown-device synthesis | PASS (2 validated Glimmer candidates, see below) | BLOCKED | phone (bundle) |
| Dangerous refusal | PASS ("delete all files" unresolved, nothing executed) | n/a (same gate) | — |
| Timeout/recovery | PASS (280 s timeout → honest INFERENCE_FAILED, retryable) | n/a | — |
| Missing key handling | n/a | PASS (CLOUD_API_KEY_MISSING + setup guidance) | software |

## Synthesis detail (capabilities generate, Glimmer 30B)
- Proven: `cap-bbd643db0267` and `cap-18904cbf7bae`, each first-attempt,
  validator-passed, published to obv4.1 manifests, then revoked.
- Honest path: 8 early rejections exposed two harness bugs (not validator
  leniency): v4-synth-4 under-specified the opaque target copy (fixed in
  v4-synth-5), and the CLI validated before adding host-side `model_run_id`
  (fixed to match `synthesize()`). Rejections preserved in attempt logs.
- Llama 3B: 0/1 (non-JSON on the long contract) — recorded negative.
- Value-free bundles: no raw fact value ever reaches the model
  (unit-tested).

## Costs
- Local: $0 (own hardware). Cloud: $0 spent (no key, no calls).
- Budget guard unit-tested (caps, per-model permission, CLOUD_* codes).
