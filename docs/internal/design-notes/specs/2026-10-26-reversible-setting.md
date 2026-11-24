# Reversible setting transaction

Implement and verify the transaction engine with a simulated screen-timeout setting before introducing a physical writer. The browser and physical adapters remain read-only during this milestone.

Scope: one exact field, screen_timeout_seconds, with proposed values limited to 15, 30, 60 or 120. Require explicit owner consent at preparation. Bind each transaction to a device identity, a target value and a hash-protected snapshot of its exact original integer value. Persist the snapshot before any mutation.

Use SQLite with a unique active-resource constraint, compare-and-set state transitions and an append-only event journal. Lifecycle: PREPARED -> VERIFIED_BACKUP -> EXECUTING -> VERIFIED -> REVERTING -> REVERTED. Ambiguous writes, unexpected read-back or external changes enter QUARANTINED. Never overwrite a value that is neither the recorded original nor the recorded target.

Idempotent apply and Undo must not repeat completed mutations. Restart recovery must use the saved original value and identity rather than inventing a new baseline. Unknown state, invalid snapshot, missing consent, unavailable device and identity mismatch block operations. Keep private journals outside the repository; public evidence contains no device identifiers.

Tests: success and exact restore, denied consent/target, durable snapshot before write, external change before apply, external change before Undo, ambiguous disconnection, restart recovery, snapshot corruption, repeated apply/Undo and concurrent attempts. Only after these pass and review finishes may a physical writer be considered. No hardware success is claimed from simulation.
