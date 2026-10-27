# Real TV relay, local Meta proposal and reusable API

On 27 October 2026, the owner-authorized headless browser driver completed the real Android TV relay journey through the Forge host. The TV observed four BLE advertisers; local **Muse Glimmer 30B** produced a validated two-step proposal; the driver checked publication consent, published a service, read it and exported its API contract. After removing the local relay key, an authenticated read returned 409. Removing the service returned 200 and its route then returned 404.

This closes the previously missing combined physical TV/HTTP/Glimmer proof. It does not mount Forge into the main server, establish general model reasoning superiority or demonstrate a new human Android permission-dialog acceptance.

## Measured successful run

| Item | Recorded result |
|---|---|
| Model | muse-glimmer:30b-q4_K_M, pinned digest in receipt |
| Execution | Local isolated CPU service on 127.0.0.1:11439; no cloud fallback |
| Input / output tokens | 259 / 98 |
| Proposal latency | 82,406 ms, excluding preload |
| Preload | 46,223 ms, no device data or generated tokens |
| Measured runner elapsed | About 152 s, including preload; prior connection/app setup excluded |
| Provider cost | $0 |
| Actual HTTP results | Publish/read/documents 200; after local key removal 409; remove 200; after removal 404 |
| Cleanup | Local relay key removed, temporary ADB forward removed, Forge host closed, own model load released |
| Android permission checks | BLE/location permission snapshots matched before/after; no grant commands issued |
| Screenshots / videos | 0 / 0 |

[Successful raw receipt](tv-glimmer-live-receipt.json). Application sources were based on 30629e6; the exact successful runner is preserved in commit **9af35cf**, and its SHA-256 matches the receipt. Later readiness-metadata changes were separately tested without another hardware inference.

## Setup, authority and privacy

The owner confirmed TV readiness and authorized handling Companion startup. Setup reconnected the single previously authorized Wi-Fi ADB endpoint and brought the installed app forward. A later process restart restored its foreground state after a launch had stalled. No APK was installed, no app data was cleared and no Android permission was granted. These setup actions happened before the successful measured runner; its zero activity-launch count must not be read as zero setup launches overall.

The product pairing APIs displayed a code on the TV. The test driver read that UI tree through authorized ADB and submitted the code. This enabled the pairing session using existing device permissions. The existing runtime primitive performed one bounded 10-second BLE scan; Forge's unmodified RuntimeV1Provider accepted only real, source-bound, fresh facts. One advertiser was selected for this verification; no named-device identity, battery, temperature or beacon-control capability was inferred.

Companion requests used an ADB forward over the authorized Wi-Fi ADB connection. The provider pseudonymized identifiers; the local model saw only capability/relay pseudonyms, evidence references, operation and simulation status. Credentials, pairing codes, addresses and raw UI trees are excluded from receipts. The temporary UI XML was removed. No screenshot/video recording was enabled.

Model output remained non-authorizing. The owner-authorized headless driver checked consent in the real Forge UI. That proves the product consent gate was exercised by the test driver, not that a human freshly accepted an Android permission dialog during this run. Existing Android permissions could originate from earlier setup/harness grants.

Local key removal and the subsequent 409 prove the local runtime/Forge authority boundary. The primitive sends a best-effort remote revoke; **remote Companion unpairing was not independently verified** and is not claimed. Only the test's own local key, temporary forward, host and model load were cleaned up; no unrelated forward or model service was stopped.

## All attempts retained

| Attempt, Paris time | Inference | Result |
|---|---|---|
| 13:06 | Valid Glimmer proposal, 255 / 90 tokens | Publication/read/documents passed; driver timed out at the revocation check; full run NOT_VERIFIED |
| 13:13 | None | Companion not foreground; readiness guard stopped the run |
| 13:15 | None | A readiness command timed out; activity-launch outcome unconfirmed |
| 13:21 | Valid Glimmer proposal, 259 / 98 tokens | Full lifecycle and required cleanup passed |

The first driver attempted a UI Test click after revocation. Controlled browser reproduction confirms that a refreshed unavailable source correctly disables that button. The corrected driver verifies server denial through an authenticated API read, then removes the service through the UI. Both controls remain intact; no timeouts or authorization checks were weakened.

[First incomplete run](tv-glimmer-first-attempt.json), [readiness attempts and count correction](tv-glimmer-readiness-attempts.json). Two actual model proposals were generated across these attempts, both locally at $0 provider cost. These attempts are evidence records, not an accuracy benchmark; the frozen v1 results remain unchanged.

## Reproduce

Requires one already-authorized connected Android TV, installed Companion, enabled Bluetooth/location as required by Android, existing scan permission, the pinned local CPU Meta service, and Playwright. These commands are explicit physical tests and are never run by CI:

```powershell
python -m dev.forge_tv_glimmer_journey --hardware
# Optional: bring only the already-installed Companion forward if needed
python -m dev.forge_tv_glimmer_journey --hardware --open-companion
```

Each invocation is a new measured attempt and can perform a new local inference and bounded scan. There is no automatic model retry. The optional launch does not install/grant permissions or clear data. A launch timeout is recorded as an unknown launch count; process restart, if needed, is deliberate setup outside this runner. Unique sanitized receipts are written under ignored artifacts/forge-physical-tv/.

Five fake-runner tests cover readiness and ambiguous launch outcomes. Four-width controlled browser checks reproduce the disabled-button case and test authenticated 409/404 responses. The pinned runtime f0de183 plus hashed current overlays passed **301 unit/integration tests**, the controlled HTTP lifecycle and seven browser modules, with zero forbidden I/O attempts in the guard. [Software receipt](tv-glimmer-software-checks.json). These guarded checks made no device/model calls; the physical run above is recorded separately.
