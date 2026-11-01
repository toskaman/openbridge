# Campaign Two §4.9 — Frontier Innovation Notes

Branch: `feat/f90-innov`. Acceptance: simulated/emulator only (no live devices).

## Candidate 1 — Portable Companion interfaces (dashboard bundles) — SELECTED

**Gap (repo reality).** `src/runtime/dashboards.py` persists named panels in the
local state file (`DashStore`) and `RemoteControls.set_controls` installs them on
one relay, but there is no export/import path: a reinstalled PC, a second PC, or
a family member's PC cannot receive an approved panel without rebuilding it by
hand. Device keys rotate every discovery, so a naive copy of stored definitions
would also point at stale keys.

**Proposal.** A versioned, integrity-sealed JSON bundle carrying labels, skills
and scalar params plus *target hints* (never trusted as keys). Import is
fail-closed: it re-verifies the seal, refuses unknown skills and `pc_run`
(`NEVER_BIND`), requires an explicit owner-supplied target remap for every
targeted control, requires consent, and installs only through the existing
`set_controls` schema path.

**Feasibility: HIGH.** Pure stdlib; reuses `DashStore`, `set_controls`, and the
`SKILLS` table; fully testable against `FakeCompanion` + the simulated routing
world. No protocol change, no new trust assumption (import consent equals the
existing install consent).

** Risks.** Bundle confused as a backup of grants — mitigated: bundles carry no
grant generations, relay keys, or approvals; import creates a fresh grant.

## Candidate 2 — Capability graph search

**Gap.** `src/fabric/capability_explorer.py` enumerates per-device capabilities
with honest statuses and `parse_followup` handles deterministic follow-ups, but
there is no ranked free-text search ("where is the mute button?") over the
explored graph.

**Feasibility: MEDIUM, not selected.** A deterministic tokenizer + ranker over
`explore()` output is easy and testable, but marginal value over the existing
`parse_followup` + Command Center NL router (`src/runtime/nl_router.py`,
`intent.py`) is small: two overlapping query paths would need disambiguation
rules, and the "frontier" delta is a nicer filter, not a new capability. Kept
as a follow-up if §4.9 scope expands.

## Candidate 3 — Learned control templates from press history

**Gap.** `RemoteControls` keeps an evidence chain per press (request id, seq,
gesture, outcome) that nothing consumes. A suggester could rank frequently
pressed controls and propose dashboard panels from real usage.

**Feasibility: MEDIUM-LOW, not selected.** The signal is thin (press counts, no
context), and the trust model (`remote_controls.py`: "the owner creates each
control") forbids silent auto-install — output could only ever be suggestions
through the existing consent path. Value is real but weaker than portability,
and any "learning" claim on bare frequencies would be dishonest. Rejected on
strength-of-delta, not on buildability.

## Candidate 4 — Safe multi-hop routing (PC → relay → relay → target)

**Gap.** `src/fabric/route_intel.py` enumerates single-hop routes with a strict
at-most-once failover rule (`UncertainOutcome` is never reissued). There is no
forwarding hop: the relay protocol (`src/fabric/relay.py`, Companion app) has
no forward primitive, no per-hop nonce binding, and no hop-count/TTL envelope.

**Feasibility: LOW, rejected.** Correct multi-hop needs a protocol change on
both ends (PC + Android Companion), a hop-aware at-most-once proof, and new
abuse controls (a relay relaying for strangers). That is a multi-branch,
two-codebase effort with live-radio failure modes that simulation cannot fully
cover — out of scope for one §4.9 increment. Documented here so a future
campaign can cost it with eyes open.

## Selection

Candidate 1 wins: highest feasibility, a genuine user-facing gap, zero new
trust assumptions, and fully verifiable in simulation. Implemented as:

- `src/runtime/dashboard_port.py` — export / verify / import (+ dry-run)
- CLI: `dashboards export`, `dashboards import`
- Oracle: `dev/f90_innov_oracle.py` (deterministic, simulated)
- Tests: `tests/runtime/test_dashboard_port.py`

## Acceptance evidence (simulated)

- Oracle `dev/f90_innov_oracle.py` passes (exit 0), receipt printed.
- `tests/runtime/test_dashboard_port.py` passes (all cases, incl. tamper,
  unknown-skill, exec-skill, unmapped-target, and consent refusals).
- Full suite green in worktree (see `logs/d2-innov.log` in the parent repo).
