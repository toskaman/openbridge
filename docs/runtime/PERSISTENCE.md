# Runtime persistence and recovery

This integration corrects PR56 while retaining its history. State lives beside the session journal in `runtime-state.json`. A missing first-run file is valid. Corrupt, unreadable, unsupported-version or malformed existing state is not reset: recovery shows `STATE_UNREADABLE`, changing operations are blocked, and route selection/arming/invocation returns an explicit 503 state error. Read-only recovery inspection remains available. Preserve the file and resolve the underlying condition before restarting; no automatic reset endpoint is provided.

## Update ordering and failure behavior

Every participating StateStore instance uses the same path-scoped thread lock plus an OS file lock (Windows byte lock or Unix flock). Read-modify-write holds that lock throughout. Temporary files have unique names, are flushed and fsynced, and are replaced atomically; Unix also syncs the containing directory. These guarantees depend on local filesystem and OS behavior, not arbitrary network shares or physical power-loss guarantees.

Policies update one skill at a time, preserving other writers' skills and receipt fields. They are published in memory only after a successful save. Failure returns `STATE_WRITE_FAILED` and blocks further routing in that process rather than claiming success. Route evaluation refreshes stored policy changes and invalidates armed consent when the affected policy changes.

Executor persistence serializes snapshot creation with saving. Unresolved receipts merge by transaction ID; explicit acknowledgement removes the saved receipt only after persistence succeeds. Retained acknowledgement tombstones prevent stale peers or delayed snapshots from resurrecting it. A save failure retains the in-memory backlog, returns the durability error in the outcome, and blocks subsequent changes. A failed acknowledgement returns HTTP503 with the recovery state, not a false success or misleading not-found result. A state error remains latched until the underlying file/storage problem is reviewed and the process restarted.

## Exact scope

- Completed unresolved changing outcomes (FAILED, PARTIAL, UNKNOWN_TIMEOUT) survive a successful save and restart. Resolved receipts are not a durable transaction history.
- This is not a pre-dispatch crash journal. Process failure before the unresolved receipt is saved can still lose that outcome; the separate session journal covers its own recorded changes only.
- File locks coordinate state updates, not cross-process device execution or a global admission cap. Run a single device-execution owner for a session.
- Acknowledgement tombstones are retained without automatic pruning. State has a 16MiB limit; exceeding it fails visibly instead of discarding recovery information. Archival/compaction requires a separate safe design.
- This change does not automatically replay, acknowledge, undo or execute anything on startup. It does not restore remote-control grants.

## Verification

Temporary-file tests cover invalid/malformed state, policy write failures, receipt/acknowledgement failures, four independent process writers, independent policy/receipt owners and stale snapshots. The API regression checks failed acknowledgement returns503. Hardware and hosted models are not involved. Physical power interruption and a full pre-dispatch crash-recovery protocol are outside this evidence.
