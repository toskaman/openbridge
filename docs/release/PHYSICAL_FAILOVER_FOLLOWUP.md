# Physical routing follow-up — 28 October 2026

**Status: PARTIAL / NOT VERIFIED end-to-end.** One bounded two-relay rerun used the owner's already-authorized Android TV and Blackview BV9300 Pro on main `0aed8a6`. No model/cloud calls, app installations, permission grants or radio/location-setting writes occurred. Two fixed wake-key requests and installed-Companion launches were used for readiness; a deliberate Companion force-stop modeled loss of the TV provider.

## Outcomes and provenance

| Stage | Recorded result |
|---|---|
| First readiness attempt | Stopped before pairing/scanning because Companion was not foreground. Failure retained. |
| Two relays paired | TV and phone paired from codes read through their own accessibility trees; temporary XML deleted. |
| TV scan | VERIFIED; retry of the same invocation returned the same transaction. |
| TV Companion stopped | Invocation BLOCKED; TV became unavailable. |
| AUTO route choice after loss | Phone selected; route_changed event recorded. |
| PINNED to the lost TV | No selected route, no silent fallback. |
| Fresh phone scan | BLOCKED. Phone Bluetooth was1 before the run and0 afterward; do not claim successful post-failover scanning. |
| Events | Seven route snapshots plus full relevant route_decision, route_changed and receipt event payloads retained. |

[Two-relay receipt](failover-evidence/partial-two-relay-run.json) and [earlier readiness refusal](failover-evidence/readiness-refused.json) retain timestamps, source revision, exact executed-driver hashes and outcomes. Corresponding `.py.txt` files retain the executed bytes for review only; they are not an automatic test runner and must not be executed implicitly. [Checksums](failover-evidence/SHA256SUMS) cover the published artifacts. Raw device serials, addresses, nearby advertiser records, pairing codes and tokens are omitted.

This run uses the real product HTTP routes (Host/Origin/CSRF, arm/invoke, signed relay traffic), a separate numeric-loopback server and a temporary session journal. Device selection was restricted to two actually connected models; only their actual discovery results were ingested. No synthetic READY or hardware result was supplied. Initial TV preference made the desired starting provider explicit, then AUTO selected the phone after TV loss. This demonstrates routing re-selection and a new attempted invocation, not transparent replay of an in-flight scan. Dead-route attempts and same-ID retries remain visible.

## Cleanup and limits

The TV Companion was reopened; both test relay entries were removed locally, only newly created forwards belonging to the selected devices were removed, and the isolated server closed. Remote cryptographic erasure/UI unpairing was not independently verified in this run. Existing unrelated forwards, services and model loads were untouched. Permission snapshots are retained. Location mode remained3 on both devices; this run preserved its observed baseline and made no settings writes. The earlier requested location restoration is still unconfirmed and must not be described as completed.

The earlier unarchived two-relay claims are not retroactively certified. This new transcript closes the artifact-availability gap for its own partial run, while leaving phone scanning unverified. No frozen gold labels/design predated this experiment: it is a demonstration, not M2 scored evaluation or model superiority evidence.

PR54 remote controls were not loaded, deployed or invoked here. Its reported repeated-action defect remains a separate do-not-merge review. No watch action or TV volume change was performed by this rerun.
