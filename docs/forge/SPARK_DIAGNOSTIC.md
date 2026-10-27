# Muse Spark cross-device diagnostic

This experimental command uses the Meta Model API (`muse-spark-1.3`) to synthesize hypotheses and ordered owner checks from a fixed synthetic USB/Wi-Fi/BLE scenario. USB inspection succeeds, TV Wi-Fi is reachable, TV relay permission is unavailable, and phone BLE evidence is stale. Transport reachability must not become permission or fresh observation evidence.

The existing fixed-priority advisor selects one step; this diagnostic asks for a cross-transport explanation, alternative hypotheses with evidence references, and owner-check dependencies. This is a richer output contract, not proof that static code cannot solve the scenario. No superiority score has been measured.

## Run one supervised request

On the owner Windows machine, with the existing DPAPI-protected credential file, run PowerShell 7:

```powershell
pwsh -NoProfile -File scripts/verify/forge_spark_diagnostic.ps1 -ObservedAt '<ISO timestamp of fresh credit confirmation>' -FreeCredits <confirmed promotional balance> -ObservationId '<unique confirmation reference>'
```

Never place the API key in arguments or Git. The wrapper loads it only after checking the five-minute confirmation window, passes it through stdin and writes a uniquely named sanitized attempt under ignored `artifacts/spark-diagnostic/`. The CLI shares `runtime-budget.sqlite` with the existing Meta broker. Each supervised session reserves $0.10 before transport, retains failed reservations, requires free-credit headroom and never retries automatically. The local reservation is an application guard, not a provider billing cap; it must not be presented as one. Paid-credit fallback is not implemented or authorized.

## Data and authority

- Only the built-in `blocked_relay` case ID is accepted; arbitrary graphs, actual device facts, names, addresses, screenshots and URLs are rejected before a call.
- The request uses the declared Meta-only model and endpoint. The response must match the model identity and contain no tool/function calls or truncated completion.
- Validation bounds prose and lists, checks evidence-key membership, allows only three read-only owner-check IDs, rejects duplicates and enforces dependencies. It does not establish semantic correctness of free-text hypotheses.
- Every result is labeled SIMULATED and non-authorizing. This module performs no ADB access, scans, permission grants, repair, publication or execution. It is not mounted into the main server or production UI.

## Evidence

Six mocked tests initially passed, including stale/missing permits, reference/order rejection, wrong-model/tool/truncation rejection and durable reservation retention. Run `python -m unittest tests.forge.test_spark_diagnostic -v` for the current suite.

One live supervised attempt on 27 October 2026 was blocked. The original CLI suppressed the specific reason, so it is unknown whether the failure occurred in transport or response validation; no root cause, usage, cost or accepted model output can be claimed from that record. The reservation remains retained. The CLI now exposes fixed safe boundary errors for future supervised attempts. No retry was made. See [failed-attempt receipt](spark-diagnostic-live-attempt.json).

The earlier Muse Spark runtime advisory remains separate successful provider evidence. The Glimmer advisor's 56/60 (93.3%) explanation result is a different task and is not reused as this diagnostic's accuracy.
