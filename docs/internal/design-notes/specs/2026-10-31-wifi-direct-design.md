# Wi-Fi direct companion transport (no ADB Wi-Fi) — design

Date: 2026-10-31. Status: APPROVED (owner). Approach B, phased.

## 1. Problem

Every PC→Companion relay call travels through `adb forward tcp:<local>
tcp:47800` (`src/adapters/android.py:forward_companion`). When ADB Wi-Fi
debugging drops (watch doze, port rotation, reboot), the whole relay dies
even though the Companion is on the LAN and the relay protocol itself is
already authenticated (HMAC-SHA256), optionally sealed (AEAD), and gated by
owner pairing codes. Observed live: S6 press stuck on "Sending…" while the
relay went offline, although the watch was pingable.

## 2. Goal

Run the full relay channel over direct LAN with zero ADB after a one-time
setup: pairing, typed/spoken orders, remote controls, dashboards, voice
clips, BLE scans, status. Maximal follow-up (same design): remote tap/type
(AccessibilityService), screenshots (MediaProjection), diagnostics dump
(one-time ADB-granted DUMP/READ_LOGS), one-tap self-update.

Non-goals: silent APK install (Android forbids it for user apps),
screenshots without the per-session MediaProjection tap, taps without the
one-time Accessibility toggle. Test tooling keeps ADB as a fallback, never
as a requirement.

## 3. Architecture

Transport selection lives in `src/adapters/android.py`:

- `direct_url(handle) -> http://<lan-ip>:47800 | None` from the
  `companion_lan` mDNS discovery record (IP + port already advertised by
  `RelayServer.registerNsd`; the server binds `0.0.0.0:47800`, no
  companion change needed for phase A).
- The relay `send` factory tries direct LAN first (3 s timeout), then the
  existing `adb forward` URL. Failover is per request; both down keeps the
  current relay-offline path untouched.
- The chosen endpoint is stored per relay (`url`, plus `lan_url`) and
  re-resolved at session start; mDNS re-discovery refreshes stale IPs.

Security is unchanged: HMAC + AEAD + pairing codes are the trust boundary,
not the tunnel. Direct LAN only widens reachability of an already
authenticated endpoint on the owner's LAN. No new open operation is added
in phase A.

Transport priority (owner order wifi → lan → adb-wifi → adb): for a handle, try the serial-IP direct URL first (whatever medium carries it), then that serial's adb forward (which rides adb-over-wifi or adb-over-USB). USB-paired devices gain a direct URL after pairing via mDNS TXT relay-id match (`lan_url_for_relay`).

## 4. Components

### 4.1 PC — phase A (no companion change)

- `android.py`: `direct_url()`, failover transport, endpoint persistence.
- `scripts/companion_wifi_setup.py`: one-time flow — ADB grants
  (`DUMP`, `READ_LOGS`, still valid after reboots until uninstall), first
  pairing, then the proof run with ADB fully disconnected
  (`adb disconnect` + drain + one control round-trip).
- Unit tests: selection prefers LAN, falls back on timeout/refused, never
  returns a URL for unknown handles, keeps per-relay endpoint isolation
  (the shared-port bug class from `forward_companion` must not regress).

### 4.2 Companion — phase 2 (new signed ops, same auth)

- `tap` / `type` / `back`: driven by an AccessibilityService the owner
  enables once in Settings. Refused with a setup hint when disabled.
- `screenshot`: single frame via MediaProjection; the owner accepts the
  system dialog once per capture session; the PC never caches the consent.
- `diag`: bounded logcat/dumpsys excerpt; works only after the one-time
  ADB grants, else an honest `unavailable` outcome.
- Self-update: version check over the relay; download over LAN; install
  through the system package installer (owner taps Install — Android's
  own consent, not ours to bypass).

Each op is a closed, bounded addition to `RelayServer`'s operation switch
with the same HMAC/nonce/expiry envelope; new capabilities are declared
(`a11y_tap`, `shot`, `diag`) so old PCs refuse cleanly instead of
mis-sending.

## 5. Data flow

Pair over either transport (identical protocol) → store both endpoints →
every poll/send tries LAN, then ADB forward → offline only if both fail.
mDNS re-discovery may move the LAN endpoint mid-session; the next request
picks it up without re-pairing (keys are endpoint-independent).

## 6. Error handling

- LAN unreachable: silent per-request failover to ADB + one debug log.
- Both down: relay offline, existing re-probe path (no behavior change).
- MediaProjection denied/expired: op returns `unavailable`, never a stale
  frame.
- Accessibility off: op refused with `setup_required` + exact Settings path.
- One-time grants missing: `diag` returns `unavailable`, never partial
  system data.
- No phantom success anywhere: every new op has an explicit outcome enum
  covered by tests.

## 7. Testing and evidence

- Unit (TDD RED→GREEN): transport selection/failover matrix, op
  request/response validation, capability gating, outcome enums.
- Live phase A: `adb disconnect` on watch + TV, then drain round-trip and
  one TV-volume control from the watch; packet capture is NOT required —
  the ADB-disconnected run is the proof.
- Live phase 2: tap/type round-trip on TV (D-pad-safe target), one
  screenshot compared against an ADB screenshot (oracle), diag excerpt
  non-empty, self-update prompt shown (install itself stays owner-tapped).
- Evidence registry row + matrix sync + screenshots under `E:/shots/`.

## 8. Rollout

Phase A first (PC only, live tonight), phase 2 after (companion build +
owner permission taps). Kill criteria: if direct LAN is unreachable on the
owner's LAN (client isolation), phase A still lands as automatic fallback
(no regression), and phase 2's new ops ride whichever transport wins.
