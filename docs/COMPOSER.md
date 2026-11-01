# Cross-Device Workflow Composer (Campaign Two §4.3)

Say what you want in plain words ("make the living room quiet"). A local Meta
model proposes a bounded multi-device workflow from your devices' actual
capabilities, the deterministic composer allows or refuses each step, and the
existing DAG engine runs whatever the composer admits.

## The three stages

1. **Propose (Meta, untrusted).** The model sees device labels, categories and
   candidate skills only — never device keys — and replies with 1–8 steps.
2. **Compose (deterministic).** Every step is checked against the live graph:
   a typed primitive, a verified device (live link required), a permitted
   route, the required authorization, a declared expected effect, an
   independent verification method and a failure strategy. Unknown skills,
   unverified devices, unpermitted routes and invalid params are refused
   openly with a reason. Any refusal blocks compilation until you revise.
3. **Run (DAG engine).** Allowed steps compile to a normal workflow with
   per-step approval for anything that is not read-only.

## Step outcomes

| Outcome | Meaning |
|---|---|
| Executed and verified | An independent read-back confirmed the effect. |
| Executed but not independently verified | The device acted; nothing confirmed it yet. |
| Refused | The deterministic engine did not run this step. |
| Failed | The step ran and failed. |
| Unknown | Outcome unknown — the device may have acted. Check recovery before retrying. |
| Reversible state restored | Reversible state restored and read back. |

## Rollback rule

**Physical acts are never atomically rolled back**: each step reports what its
device confirmed, and only state with a verified read-back is ever marked
restored. Exact-reversible steps offer per-step restore through the undo
primitive, never an atomic multi-device rollback.

## Interfaces

- HTTP: `GET /api/v2/composer/catalog`, `POST /api/v2/composer/compose`
  (dry run, no consent needed), `GET /api/v2/composer/summary?workflow_id=…`.
- CLI: `workflows compose "…"`, `workflows summary <id>`.
