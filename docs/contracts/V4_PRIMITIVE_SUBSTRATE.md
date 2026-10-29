# V4 primitive substrate (Claude): contract, registry and handoff

Status: implemented on branch `feature/v4-primitive-substrate-claude` (base main dcf8527); SIMULATED_VERIFIED by tests.
No physical run of a Meta-generated manifest yet: that needs an owner-supervised session (see "Owner approvals needed").
Ownership (01_COORDINATION/01_AGENT_OWNERSHIP.md): this is the substrate. Device-specific capability content,
UI plans and workflows come from the Meta tier (Muse Code at development time, Muse models at runtime).

## BASELINE_COMMIT
`main` dcf8527 (PR #70). Reused, not rewritten: Executor (consent, locks, receipts, recovery backlog, durable state),
B2 routing, B3 Companion channel (signed relay, per-control grants, at-most-once, hold-to-send), the Android action adapter, Tuya and relay adapters.

## Contract (`src/substrate/v4_contract.schema.json`, version `obv4.1`)
One canonical schema, all document types in `$defs`:
- `Fact`
- `PrimitiveDescriptor`
- `CandidateManifest` (origin `meta_generated`)
- `InvokeRequest`
- `Grant`
- `Receipt`
- `EngineeringPrimitiveRequest`
- `UIViewPlan`

Cross-field rules live in `src/substrate/kernel.py`. Shared fixtures (test key `b"k"*32`, clock 1800000000) are in `tests/substrate/fixtures/`.

## API (all under the existing local server; POST = CSRF + Origin, owner path)
| Route | What |
|---|---|
| `GET /api/v2/primitives/catalog` | NATIVE_PRIMITIVE_REGISTRY + the contract schema (what Muse tooling may read) |
| `GET /api/v2/facts/signed?device=` | Signed, timestamped facts and the keyed device fingerprint (EvidenceBundle) |
| `POST /api/v2/manifests/compile` | Dry run: schema, primitives, typed args, permissions, facts, bounds, injection. No side effect, no grant. Unsupported → `REJECTED_UNSUPPORTED_PRIMITIVE` + `engineering_request` |
| `POST /api/v2/manifests/grant` | Owner approval bound to manifest hash, device fingerprint, permissions, uses and expiry (HMAC, server-only key) |
| `POST /api/v2/manifests/revoke` | Revoke a grant (checked again before every step) |
| `POST /api/v2/manifests/invoke` | Execute an approved manifest → signed `Receipt` |
| `POST /api/v2/manifests/ui_install` | Validated `UIViewPlan` → Companion buttons bound to approved manifests (B3 channel) |
| `GET /api/v2/manifests/receipts` | Last signed receipts |

## SECURITY_CONTRACT (each line has a test in `tests/substrate/test_kernel.py`)
**Primitives and manifest shape**
- Unknown, HYPOTHESIS, BLOCKED and owner-only (`pc.job`, shutdown) primitives are rejected, with an EngineeringPrimitiveRequest; there is no shell or ADB primitive for models.
- Arguments are typed against the primitive input schema; extra arguments, out-of-enum values and control, template or script markers are rejected; only declared `$input` and required `$fact` references resolve.
- Static bounds: at most 12 steps, at most 20 dispatches, at most 3 repetitions of an irreversible step.

**Permissions, target and facts**
- Declared permissions must cover the steps, and the device link must grant them (no privilege expansion).
- The target is a keyed fingerprint of the device's strong identity: forged, swapped or other-device targets are rejected; a physical device swap after approval blocks execution.
- Facts must be server-signed, fresh (`max_fact_age_s`), from the target device and unchanged; a forged fact fails.

**Approvals**
- Grants come only from the owner path and are HMAC-signed. A model-widened or model-minted grant fails, and the manifest hash binds the exact version (any edit needs a new approval).
- Uses, expiry and revocation are enforced. An operation id cannot be replayed.

**Execution and receipts**
- Facts, permissions, target and revocation are re-checked before every step; a downgrade between steps stops the rest (BLOCKED).
- An uncertain outcome (FAILED, PARTIAL, UNKNOWN_TIMEOUT) is never retried: `INCONCLUSIVE`.
- Receipts are signed; `origin` keeps `meta_generated` distinct from `prebuilt`.
- UI plans: the hash is recomputed, the target must equal the relay's device, labels only reach the device, a revoked grant blocks the press, and grants are never exposed by GET.

## NATIVE_PRIMITIVE_REGISTRY (`src/substrate/registry.py`)
| id | platform | side effect | permissions | status | manifest |
|---|---|---|---|---|---|
| device.read_descriptor | any | READ | read | REAL_HARDWARE_VERIFIED | yes |
| device.probe_actions | android | READ | read | REAL_HARDWARE_VERIFIED | yes |
| state.read_setting | android | READ | read | REAL_HARDWARE_VERIFIED | yes |
| state.screen | android | READ | read | REAL_HARDWARE_VERIFIED | yes |
| app.list | android | READ | read | REAL_HARDWARE_VERIFIED | yes |
| input.key | android | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| app.launch | android | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| url.open | android | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| input.text | android | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| input.tap | android | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| setting.set_exact | android | REVERSIBLE_EXACT | control | REAL_HARDWARE_VERIFIED | yes |
| setting.restore | android | REVERSIBLE_EXACT | control | REAL_HARDWARE_VERIFIED | yes |
| ble.scan_via_relay | ble_relay | SESSION_CLEANUP | control | REAL_HARDWARE_VERIFIED | yes |
| vendor.tuya.command | tuya | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | yes |
| vendor.tuya.setting_exact | tuya | REVERSIBLE_EXACT | control | REAL_HARDWARE_VERIFIED | yes |
| pc.job | windows | IRREVERSIBLE | control | REAL_HARDWARE_VERIFIED | no |
| files.open_user_granted_uri | android | READ | read | HYPOTHESIS | yes |
| files.transfer_chunks | any | SESSION_CLEANUP | control | HYPOTHESIS | yes |
| screen.capture_session_approved | android | READ | read | HYPOTHESIS | yes |
| screen.present_image | android | SESSION_CLEANUP | control | HYPOTHESIS | yes |
| calls.request_contact_lookup | android | READ | read | HYPOTHESIS | yes |
| calls.place_call_with_confirmation | android | IRREVERSIBLE | control | HYPOTHESIS | yes |
| remote.request_shutdown | windows | IRREVERSIBLE | control | BLOCKED | no |

## PLATFORM_CAPABILITY_FACTS (what is proven vs hypothesis)
- **Proven on owned hardware:**
  - Android/TV/Wear OS keys, app launch, URL, text, tap (vendor-blocked on MIUI), settings with exact read-back and restore.
  - BLE scan through phone/TV relays, with failover (B2 run, 28 Oct).
  - Tuya vacuum start, pause and dock, plus exact settings.
  - Watch → PC → TV control with one execution per hold (B3 run, 28 Oct).
- **Simulated only:** the manifest pipeline end to end (this PR).

## UNSUPPORTED_OS_LIMITS (honest blockers)
- **No OS-approved screen capture session yet.** `adb screencap` is not MediaProjection, and whole-screen capture of the TV or watch depends on the OS.
- **No file primitive yet** (SAF grant, chunked AEAD transfer, SHA-256): `files.*` is HYPOTHESIS.
- **No contact or call primitive yet.** The phone dials via `ACTION_DIAL` after owner confirmation. TV or remote-mic call audio is not claimed.
- **Shutdown is BLOCKED** until step-up voice + local approval exists.
- **BLE scan ≠ GATT / pairing / audio / file transfer.**

## MUSE_HANDOFF
1. Read the catalog and signed facts. Emit `CandidateManifest` documents with `origin: meta_generated`, a real `model_run`, and `evidence_refs` that point at the signed fact ids or inspected sources.
2. Call `compile` first. On `REJECTED_UNSUPPORTED_PRIMITIVE`, surface the returned `engineering_request` (`NO_SUPPORTED_PRIMITIVE`) instead of inventing a route.
3. Emit `UIViewPlan` with `plan_hash = sha256` of the canonical plan without `plan_hash` (see fixtures). Buttons bind to manifest hashes.
4. Never request a grant: approval is an owner UI action. The kernel rejects any self-made grant.

## SOL_HANDOFF
- Attack surface: the eight routes above.
- Tests: `python -m unittest tests.substrate.test_kernel` (25 tests, mainly security-negative) plus the full suite (623 OK locally).
- Points to red-team:
  - fact freshness vs registry update timing;
  - hash canonicalization (`json.dumps` sort_keys, no NaN);
  - grant replay across server restarts (the key is per process, so grants die at restart by design);
  - Companion label rendering limits.

## OWNER_APPROVALS_NEEDED
1. A supervised run: one Meta-generated manifest + UI plan on the TV/watch, then revoke, with physical receipts. It needs the Muse tier output.
2. Any new platform primitive from the HYPOTHESIS list (files, capture, contacts or dial) before implementation on devices.
