# Routing evaluation implementation plan

**Goal:** Freeze and run a transparent synthetic B2 routing benchmark without hardware or model calls.
**Architecture:** Separate immutable cases/gold/registration from the production-router adapter and independent baselines. Temporary contexts use fake transports and refusing runners. Retain complete documents and errors.
**Tech stack:** Python standard library, existing Registry/Router, unittest.

- [x] Review existing M2 grid, fixtures and production routing semantics.
- [x] Freeze 32 input snapshots, separate construction-based gold and registration; commit before scored execution.
- [x] Add dev/evaluate_routing.py with hash guard, independent raw-input baselines, isolated adapter, reports and no-overwrite CLI.
- [x] Write failed-first tests using development cases only: hash refusal, label isolation, abstention metrics, baseline ordering, dispatch refusal and output preservation.
- [x] Independently review the frozen design and implementation before scoring. Record the scope of that review; no hosted Spark review is fabricated.
- [x] Commit the exact harness, then run once against the frozen inputs. Retain failures without tuning cases or runtime.
- [ ] Publish results with exact provenance, limitations, local verification and CI evidence. Update team checkpoint and release backlog.
