# G3 sealed held-out task — protocol and candidate pool

Purpose: turn the passing G3 *integration smoke* (TV mute, a public target) into a **held-out** demonstration:
a task that no one can tune toward, chosen and frozen by Sol (independent auditor) before the run.

## Commit → run → reveal
1. **Freeze the model side first.** The synthesis prompt (`PROMPT_VERSION` in `src/forge/v4_synthesize.py`,
   currently `v4-synth-3`) and the runner (`dev/run_g3_smoke.py`, `dev/g3_task.py`) are pinned by commit hash in
   Sol's commitment comment. No prompt, runner or registry change after the commitment.
2. **Sol writes the spec privately** (format below, validated by `dev/g3_task.validate`) and publishes ONLY
   `sha256(canonical spec)` (`python -c "from dev import g3_task as G, json; print(G.spec_sha256(json.load(open('spec.json'))))"`)
   in a PR comment, plus the pinned commit hashes. The spec file stays off the repo.
3. **Run (owner present):** Sol hands the spec file to the owner/runner at run time:
   `python -m dev.run_g3_smoke ... --task-spec spec.json --task-sha256 <committed>`. The runner refuses any
   spec whose hash differs. The model sees only `intent`, the live evidence projection and the offered primitives.
4. **Reveal:** the spec and the transcript (`kind: G3_SEALED_TASK`, `task_sha256`) are published together,
   whatever the outcome. KILLs and failures are reported, never retried beyond the frozen budget.

## What the spec fixes (independent of the model)
| field | meaning |
|---|---|
| `intent` | the only task text the model receives (10–200 chars) |
| `offer` | primitive ids exposed to the model (must be manifest-allowed) |
| `allowed_effects` | the EXACT non-READ steps the owner consents to; any other plan is KILLed before the grant |
| `oracle` | independent read through the Executor (`audio_state` / `screen_state` / `get`) and the field checked |
| `expect.value` | value the oracle must show after the act (a pre-run value already equal = no-op, scores nothing) |
| `restore` | `reinvoke` (toggle tasks) or a deterministic `owner_action` (`set` with `$pre`, `key`), never model-driven |

SUCCESS = act executed → oracle shows `expect` → restore succeeds → oracle field equals the pre-run value →
grant revoked → invoke after revoke refused. Everything else is KILL or FAILED_ORACLE.

## Candidate pool (Sol may pick one, change the value, or write a new task)
Eligibility: every primitive is `REAL_HARDWARE_VERIFIED`, the oracle is independent of the manifest, the effect
is reversible, and **no prebuilt skill covers the task**. Current prebuilt skills: `ble_scan_room`, `device_facts`,
`tv_volume_set`, `tv_volume_step`, `vacuum.start/pause/dock`, `fabric.status`. So volume tasks are excluded
(stocked), and so is TV mute (public smoke).

| id | target | effect (allowed_effects) | oracle | restore | notes |
|---|---|---|---|---|---|
| P1 | tv | `setting.set_exact {setting: screen_timeout_ms, value: <Sol>}` | `get screen_timeout_ms` → value | `owner_action set $pre` | value in the measured range |
| P2 | phone | `setting.set_exact {setting: screen_brightness, value: <Sol>}` | `get screen_brightness` → value | `owner_action set $pre` | phone must be awake |
| P3 | tv | `app.launch {package: <Sol, from app.list>}` | `screen_state` → focused_app | `owner_action key home` | `expect` = package; the owner presses Home before the run so pre = launcher, which restore returns to |
| P4 | phone | `setting.set_exact {setting: screen_timeout_ms, value: <Sol>}` | `get screen_timeout_ms` → value | `owner_action set $pre` | |

Sol chooses the value or package secretly; the pool being public does not reveal it.

## Baseline (fair ablation, recorded in every transcript)
RulesPlanner output plus whether a prebuilt skill covers the task. For P1–P4 no prebuilt skill exists; the
generic Executor primitive exists, which is exactly the point: the model has to compose it from the intent.

## Budget
Per run: allowance ≤ $0.80 per owner observation, global ledger cap $2.00 (owner-ordered). At most 3 model calls
per run, no retry after a transport failure. A fresh owner observation (balance + time + authz text) is needed.
