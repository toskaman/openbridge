# Physical demo runbook — §5 Meta→device panel, §6 watch chain

Owner-gated: every step below needs awake hardware AND the owner present.
Preparation (this file + `scripts/verify/demo_preflight.py`) is permitted
unattended; execution is not. No recording without explicit media authorization.

Prior art: `s5-tv-panel-31oct` (TV panel → vacuum dispatch, vacuum already
docked, press injected via ADB) and `s4-quiet-mode-31oct` (reversible quiet
mode with read-back). This runbook closes the two gaps: observable motion and
a manual press.

## 0. Preconditions

- Owner present, awake, and consenting; media authorization confirmed or declined.
- Hardware awake: Owner Android TV, Owner Tuya robot vacuum (undocked, in an
  owner-approved safe area), Galaxy Watch7 (awake, not dozing).
- Companion 0.12.0+ installed on TV and watch; PC server on this branch.
- Vacuum safe area agreed with the owner before anything moves.

## 1. Preflight gate (read-only, runnable anytime)

```powershell
python scripts/verify/demo_preflight.py --timeout 30
```

- Exit 0: TV + vacuum + watch all reachable → GO for §5 and §6.
- Exit 2: partial (prints which leg is missing) → run the reachable half only.
- Exit 3: nothing reachable → NO-GO, stop, record the outcome.

The preflight never pairs, installs, commands, or moves anything. It prints
aliases only; serials, IPs, and keys are redacted.

## 2. §5 runbook — "Create a control panel on my TV so I can operate my robot vacuum"

| # | Action | Expected | Evidence to capture |
|---|--------|----------|---------------------|
| 1 | Owner types the request in Ask OpenBridge | Request accepted | Request text + timestamp |
| 2 | `devices discover` shows TV + vacuum | Both aliases listed | Discovery output |
| 3 | Capability manifest sent to local Meta model | Model ID + digest logged | Model identity |
| 4 | Model proposes control schema | Schema rendered for review | Generated schema JSON |
| 5 | Strict validator checks targets/commands/params | VALID verdict | Validator output |
| 6 | Owner reviews and approves | Approval recorded | Consent record |
| 7 | Install controls on the real TV | Installation receipt | Receipt + transaction ID |
| 8 | Controls render in the TV Companion | Visible panel on TV | TV photo/screenshot |
| 9 | Owner presses ONE control manually | Press observed | Interaction note (manual, not ADB) |
| 10 | Command travels the authenticated channel | Signed relay log | Relay transcript excerpt |
| 11 | Tuya operation dispatched | Dispatch receipt | Receipt |
| 12 | Vacuum exhibits an observable result | Motion or state change seen | Independent oracle note (second observer or video frame) |
| 13 | Outcome + limitations recorded | Ledger entry | Ledger excerpt |
| 14 | Control revoked | Revocation receipt | Receipt |
| 15 | A further invocation is denied | DENIED/REVOKED verdict | Refusal record (§9 channel) |
| 16 | Temporary state cleaned up | `devices status` clean | Cleanup confirmation |

Fallback: if motion is unavailable, keep the verified-dispatch claim only and
state the missing observation. Never invent movement; never pass simulated
footage as physical proof.

## 3. §6 runbook — Galaxy Watch7 → TV or vacuum

| # | Action | Expected | Evidence to capture |
|---|--------|----------|---------------------|
| 1 | Discover the watch via LAN/Companion | Watch alias listed | Discovery output |
| 2 | Verify the watch is awake and reachable | Liveness probe OK | Probe output |
| 3 | Confirm the signed pairing | Pairing receipt | Receipt |
| 4 | Load an owner-approved capability | Grant record | Grant |
| 5 | Render natively on the watch | QUICK CONTROLS visible | Watch photo |
| 6 | Owner performs a real interaction | Press observed | Interaction note (manual) |
| 7 | Request observed at OpenBridge | `remote_request` event | Event excerpt |
| 8 | Consent/lease/identity/target validated | VALID verdict | Validator output |
| 9 | Exactly one action dispatched | Single receipt | Receipt |
| 10 | Outcome verified via an independent channel | Read-back or observation | Oracle note |
| 11 | Capability revoked | Revocation receipt | Receipt |
| 12 | Subsequent invocation denied | DENIED verdict | Refusal record (§9 channel) |

Rules: honor watch sleep truthfully; no blind retry after an uncertain
dispatch; no phantom success; no repeated command on reconnect. If a manual
gesture is required, the owner performs it.

## 4. Shot list (photos/screenshots, owner-authorized only)

1. Ask OpenBridge request + model identity on screen.
2. Generated schema + VALID verdict.
3. TV Companion showing the installed panel.
4. Owner's manual press (hands visible, no ADB overlay).
5. Vacuum mid-action or changed state (timestamped).
6. Watch QUICK CONTROLS rendering the capability.
7. Revocation + denied re-invocation in the Activity timeline (§9 panel).
8. Cleanup confirmation.

Store captures under `E:/shots/` with `demo-s5-` / `demo-s6-` prefixes and log
each file in the §22 report table. Serials, IPs, and keys must be redacted
before anything leaves this PC.

## 5. Cleanup (every run, pass or fail)

- Revoke all demo grants; verify denied re-invocation.
- Confirm the vacuum is docked or parked safe; confirm the TV shows no stale panel.
- Remove temporary journals; record the final state in the report.
