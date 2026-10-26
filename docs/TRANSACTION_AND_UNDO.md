# Transactions and Undo

Engine: src/core/transactions.py (SQLite, durable snapshot before write, unique active resource, compare-and-set states PREPARED -> VERIFIED_BACKUP -> EXECUTING -> VERIFIED -> REVERTING -> REVERTED, QUARANTINED on ambiguity; external changes never overwritten).
Physical adapter: src/adapters/android_package.py — one allowlisted optional app, Android user 0 only (active user checked), exact enabled-state code (0 default / 1 enabled / 3 disabled-user) read from dumpsys and cross-checked with pm lists; identity (USB authorization + build fingerprint) re-checked before every read/write. The engine refuses before writing when exact restoration is impossible (`can_restore`: default state before Android 9). Router/box writes: none (read-only by policy).
Agent flow: OBSERVE -> META PLAN -> deterministic GATE -> owner CONSENT -> SNAPSHOT/EXECUTE -> independent READ-BACK -> Undo or journal RECOVERY after crash (planning blocked while a change is pending).
Real evidence: physical-package-receipt.json, agent-loop-receipt.json, crash-recovery-receipt.json.
