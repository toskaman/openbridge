# §4 quiet-mode proof: Meta-planned TV + vacuum workflow (REAL_HARDWARE, 31 Oct 2026)

Owner scenario (P30 §4): "I'm going to bed. Put my living room in quiet
mode: lower the TV volume and send my robot vacuum back to its dock."

## Chain under test

NL text → `workflows plan` → Llama 3.2 3B (local, temp 0, JSON-schema
constrained) → strict validator (`src/runtime/nl_plan.py`: unknown
skill/target/param → PLAN_REJECTED) → owner consent → trusted Router +
workflow DAG executor (`src/runtime/workflows.py`, `src/runtime/routing.py`).
The model proposes; deterministic gates dispose. No parallel agent engine.

## What was built for this proof

- `src/runtime/nl_plan.py` (new): NL→workflow bridge, 16/16 tests.
- `Router.resolve_target` (`src/runtime/routing.py`): labels are the stable
  reference; device keys rotate every discovery, so dispatch resolves the
  label to the live key at dispatch time, in every process.
- `workflows approve <wid> <step> [--deny] --consent <token>` (`src/cli.py`):
  per-step approval with preview-bound consent; no CLI approve path existed.
- `_drive` WAITING fix (`src/runtime/workflows.py`): re-drive after a
  sibling approval used to skip pre-existing WAITING steps and finalize
  `done`, stranding the sibling forever (found live, see honest trail).

## Proof transcript (wf-a44e6e7a62b7, all times UTC 31 Oct 2026)

Model: `llama3.2:3b` via Ollama `http://127.0.0.1:11434`
(reply_sha256 `bfdbc945e12221e6…`, deterministic: same sha for the
equivalent first-attempt text).

Plan (validator-accepted, consent `1b62326dd7bce46c`):

```
- step1 tv_volume_step -> 'android tv' {'direction': 'down'}
- step2 vacuum_command -> 'Robot vacuum (Tuya)' {'command': 'dock'}
```

Run → `waiting_approval` (step1 WAITING, step2 WAITING).
Approve step1 (preview-bound consent `de2a0e4f43b88f09`) → step1 EXECUTED
(receipt EXECUTED, verified true, tx-6e6113cbe743eb53), record back to
`waiting_approval`, step2 still WAITING (the fix, verified live).
Approve step2 (consent `177cab7288d5518d`) → step2 EXECUTED, record `done`.

TV leg (target 1, ADB 192.168.1.15:5555, `dumpsys audio`, independent oracle):

```
pre : STREAM_MUSIC streamVolume:22  (speaker volume_music_speaker=8)
post: STREAM_MUSIC streamVolume:21
```

Exactly one step down, one dispatch, no duplicate physical action.
VERIFIED.

Vacuum leg (target 2, Tuya LAN 3.4 at 192.168.1.25, tinytuya read-back):

```
pre : vacuum_status=charge_done battery=100% fault=0
cmd : dock (chargego) acknowledged, tx-5f4244c4c0c05ab6
post: vacuum_status=charge_done battery=100% fault=0 (independent re-read)
```

The robot was already docked, so no docking motion could occur or be
observed. Receipt state VERIFIED refers to ack + consistent read-back
(`reversible: false` correctly labeled). Per §4's own rule — an
acknowledged command does not prove physical docking — this leg is
EXECUTED_ON_HARDWARE with read-back, NOT a verified physical-docking
claim. No start/move issued (night, docked).

Device keys rotated between every process (dev-829e… → dev-4532… →
dev-9ee0…/dev-12a9…); label resolution held across all of them.

## Honest trail (first attempt failed twice, both preserved)

1. First plan/run (wf-8f8bb8344eaa): approval-parked workflow resumed in a
   new process hit a stale device key → ROUTE_NOT_SELECTED. Root cause:
   keys rotate every discovery. Fixed by labels-as-stable-refs +
   dispatch-time resolution (tests: `test_dispatch_resolves_label_to_live_key`,
   `ResolveTarget`, `ResolveTargetsTests`).
2. Second run (wf-5aa0bbe0a3fc): approving step1 finalized the record
   `done` with step2 stranded WAITING — the `_drive` bug above. Record
   preserved in the local journal as found evidence. Fixed + regression
   test `test_approval_sibling_stays_waiting_until_approved` (RED→GREEN).

## Reversibility shown to the owner

- `tv_volume_step`: skill-level IRREVERSIBLE (conservative B2 label: a
  single press carries no read-back Undo; exact rollback exists only via
  `tv_volume_set` with measured range). The two proof presses (23→22→21)
  were left in place; restore via `tv_volume_set` on request.
- `vacuum_command dock`: IRREVERSIBLE, correctly surfaced.

## Limitations

- Vacuum physical-docking motion not demonstrated (already docked).
- Single scenario (n=1 end-to-end); generalization is NOT claimed —
  see §6 eval design for the frozen benchmark.
- TV route needs ADB/Wi-Fi + control grant; vacuum needs owner-linked
  `tuya.json` (outside the repo, never logged).
