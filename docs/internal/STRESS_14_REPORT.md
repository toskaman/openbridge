# §14 Stress report — §7 paths (2026-10-30)

Scope: concurrency and storage hardening for the §7 orchestration paths
(workflow runtime, capture/transfer store). Pre-existing authorization,
network, model and drill coverage is untouched; every finding below ships
with its regression test.

## Findings (all fixed)
1. **HIGH — concurrent `run()` with the same workflow id double-dispatched.**
   Two threads both saw an empty journal and drove the DAG twice. Fix:
   per-id in-process lock + store check inside the lock + approve/cancel
   locked the same way. Test: `test_concurrent_same_id_dispatches_once`,
   `test_concurrent_approve_dispatches_once`.
2. **MEDIUM — cross-instance capture-store index race.** Runners build
   short-lived store instances, so the per-instance lock could not serialize
   parallel steps; concurrent puts overwrote each other's index entries
   (orphaned files, early eviction). Fix: process-wide lock per store root.
   Test: `test_parallel_puts_keep_index_complete` (16 threads x 20 puts).
3. **MEDIUM — no total byte cap.** 64 files x 32 MB could reach 2 GB next to
   the state file. Fix: 256 MB total cap with oldest-first eviction, and a
   single file bigger than the cap is rejected. Tests:
   `test_total_bytes_cap_evicts_oldest`,
   `test_single_file_bigger_than_cap_rejected`.
4. **LOW — raw `OSError` leaked from store IO.** Disk failures surfaced as
   bare OS errors instead of typed failures. Fix: wrapped as `StoreError`
   (missing ids still report unknown-id). Test:
   `test_os_errors_surface_as_store_errors`.

## Not claimed
Long-session leak profiling, WAN chaos (latency/loss/reorder) and model
OOM/token-exhaustion drills remain future work; no production-readiness
claim is made on those axes.
