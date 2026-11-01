# Watch voice loop over direct LAN (31 Oct 2026 23:16 UTC / 1 Nov 00:16 CET)

Three owner-spoken French orders on the Galaxy Watch7, drained over plain
Wi-Fi (no watch adb), transcribed locally on the PC, parsed, and reported
back with signed receipts. Run vehicle: `.xbuild/v_watch_voice.py`
(uncommitted session tooling). Nothing is executed from this channel —
reports only, by design.

## Results (3/3 drained + reported, exit 0)

| # | Heard (local STT, verbatim) | Parse outcome |
|---|---|---|
| 1 | "enlève les boutons de volumes de la montre et met les bouton" | needs_clarification ("Set an ex…", truncated in log) |
| 2 | "mas les boutons de volume sur la tellée" | needs_clarification ("Mas les boutons de volume sur …") |
| 3 | "mais les boutons de volume sur la tellée" | needs_clarification ("Set un volume exact, ou faire …") |

Quotes are the `[drain]` stderr lines (truncated at 80 chars by the logger);
full lines live in the session tool output, transcripts above are exact.

## What this proves

- Voice clips (PCM16) are announced via `get_commands` and fetched over the
  direct-LAN URL through the sealed aead1 channel — no adb at any step.
- Local transcription + local parse + signed `report_command` round-trip all
  succeeded for all 3 clips (HMAC-verified replies).
- No wrong-skill outcome: imperfect transcripts still route to clarification
  questions, never to actions.

## Honest limitations

- STT quality is usable but imperfect: "mets" → "mas"/"mais", "télé" →
  "tellée" (local model + watch mic + night-time speech).
- No watch screenshots (no watch adb in this setup); on-watch captions were
  delivered (signed receipts) but not visually confirmed.
- The watch slept near the end of the 6-minute window: 3 tail polls timed
  out (`URLError WinError 10060`). The drain collected the errors, kept the
  3 reports, and exited 0 — graceful degradation, same known
  relay-sleeps-with-screen limitation as every watch run.

## Owner intent observed (not executed)

All 3 orders ask for the same thing: remove the volume buttons from the
watch and put volume controls on the TV instead. Recorded here as a feature
request for a later session; no control layout was changed by this run.
