# Watch voice loop over direct LAN (31 Oct 2026 23:16 UTC / 1 Nov 00:16 CET)

Three owner-spoken French orders on the Galaxy Watch7, drained over plain
Wi-Fi (no watch adb), transcribed locally on the PC, parsed, and reported
back with signed receipts. Run vehicle: `.xbuild/v_watch_voice.py`
(uncommitted session tooling). Nothing is executed from this channel —
reports only, by design.

## Results (3/3 drained + reported, exit 0)

Counts: `E:\shots\voice-loop-log.json` orders show reported 1+2=3
(per-poll fresh stats); exit 0 gates ≥1 report (vehicle returns 0 when
n>=1), the 3-count comes from the log plus session stderr. Each reported
increment requires successful fetch+transcribe+parse and an HMAC-verified
report reply, so 3× reported entails 3× signed round-trips.

| # | Heard (local STT, verbatim) | Parse outcome |
|---|---|---|
| 1 | "enlève les boutons de volumes de la montre et met les bouton" | needs_clarification ("Set an ex…", truncated in log) |
| 2 | "mas les boutons de volume sur la tellée" | needs_clarification ("Mas les boutons de volume sur …") |
| 3 | "mais les boutons de volume sur la tellée" | needs_clarification ("Set un volume exact, ou faire …") |

Heard quotes are `heard[:60]` inside `[drain]` stderr log lines cut at 80
chars (`src/runtime/command_drain.py`: Heard cut at `:82`, log line cut at
`:107` — an earlier revision conflated the two). Row 1 hits the 60-char
limit exactly and ends mid-phrase, so its tail is unknown; the earlier
"transcripts above are exact" claim is corrected here. Rows 2–3 are
complete (<60 chars). Outcome quotes are truncated. The quoted lines lived
in ephemeral session output (no persisted drain stderr for this run;
`E:\shots\drain-live\watch.log` holds different transcripts from another
session).

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
- The watch slept near the end of the 6-minute window: tail polls timed
  out (`URLError WinError 10060`; one unique error persisted in
  `voice-loop-log.json` because the vehicle dedupes identical strings —
  the count 3 comes from live stderr). The drain collected the errors,
  kept the 3 reports, and exited 0 — graceful degradation, same known
  relay-sleeps-with-screen limitation as every watch run.

## Owner intent observed (not executed)

Orders #2–3 ask to put volume buttons on the TV; #1 asks to remove them
from the watch, with its tail cut at 60 chars. Read together as one feature
request — remove the volume buttons from the watch and put volume controls
on the TV instead (human synthesis, not machine parse; no order was
resolved to an action, all 3 went to clarification). Recorded here for a
later session; no control layout was changed by this run.
