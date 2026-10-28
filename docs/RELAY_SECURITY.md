# Relay and remote-control security model (B3)

Scope: OpenBridge Companion relays (Android phone, TV, Wear OS watch) paired with one OpenBridge PC, and the
owner-authorized remote controls they expose. Written for review; describes what the code enforces today.

## Assets and actors
- **Owner**: the person at the PC. Creates every control and every relay pairing.
- **PC**: the only place where skill, target and parameters of a control live, and where every action is routed (B2),
  consented and executed (Executor receipts, recovery backlog).
- **Companion**: holds a pairing key and, for remote controls, only `{control_id, label}` pairs.

## What a paired device can and cannot do
| Can | Cannot |
|---|---|
| Report BLE scan results when the PC asks (bounded, validated) | Choose the skill, target or parameters of a control |
| Queue a request `{request_id, control_id, seq, pressed_at, gesture, touch}` for a control the owner granted | Invent a control: unknown ids are dropped |
| Show the PC's signed outcome | Make the PC repeat an action: a request id runs once (invocation ledger); failed or uncertain outcomes are never reissued |
| | Reach the PC on its own: the PC polls over the signed relay channel; nothing listens on the PC for the device |

## Enforced checks (PC side, at the moment of dispatch)
- The control's grant generation still exists. A re-grant gets new ids, a revoke drops the grant, and both are checked under the lock right before invoke.
- The relay key fingerprint still matches; re-pairing invalidates the grants.
- The request time on the device is within ±30 s.
- The B2 route is selected and READY, and the lease is bound to actor `relay:<id>`, target identity, authority revision and exact params.
- Per-control rate limit (0.5 s), and suspension after more than 3 requests in 10 s until the owner re-grants.
- Shutdown (`server_close`) stops the poller and new dispatch admissions. An operation already admitted before shutdown or revocation may finish; this is not physical cancellation.
- Delayed owner-grant responses cannot restore a control after a newer revocation. The PC checks the latest per-relay update generation and pairing key before installing a grant. A device card can lag during concurrent updates; stale ids remain unauthorized on the PC.

## Device side
- **Hold to send:** a tap sends nothing; a long press is required.
- **One press in flight per control:** the button shows "Sending…" and is disabled until the PC's signed result arrives or 20 s pass.
- **At-most-once delivery:** a request fetched by the PC and not answered shows "Not confirmed" and is never re-sent. The owner checks the device and presses again.

## Residual risks (accepted, documented)
1. **No on-device user authentication.** Anyone holding the paired, unlocked watch or phone can press granted controls. Impact is bounded by what the owner granted (skills, target, params), by revocation from the PC and by the rate limit and burst suspension.
   - Mitigation: grant only controls you would accept from anyone holding the device.
   - Optional follow-up: require the device keyguard to be locked-and-unlocked recently.
2. **At-most-once delivery can lose a press**, e.g. if the PC crashes between fetching and dispatching it. The device shows "Not confirmed"; nothing is retried automatically.
3. **Phantom touches on an unworn watch.** On 28 Oct, 2 taps on the first build led to 16 executions. With hold-to-send, one press in flight, burst suspension and the recorded gesture/touch evidence, the owner-attended run showed one hold → one execution. The original cause stays unproven.
4. **LAN transport.** Relay traffic goes over an `adb forward`, which is local to the PC. Messages are HMAC-signed with a key derived from the on-screen pairing code (PBKDF2, 200k iterations), with nonces that expire. They are not encrypted.

Owner control pushes are serialized through acknowledgement and local publication, with a generation check before sending. A newer owner update revokes local authority immediately while waiting for an older push to finish; after successful acknowledgements, Companion buttons and local grants converge to the newest update. Transport failure can leave device presentation uncertain; stale IDs remain denied locally.
