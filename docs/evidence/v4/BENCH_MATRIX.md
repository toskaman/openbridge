# Benchmark matrix — Meta route vs deterministic route (29 Oct 2026, $0 new spend)

Compiled from VERIFIED in-repo evidence only. No new model spend was used for
this matrix (ledger preserved at $1.30/$2.00 for the sealed run).

| task | Meta route | deterministic route | verdict (honest) |
|---|---|---|---|
| Manifest synthesis, 8 dev cases (S1) | llama3B 0/8 (copy-exact fail) | RulesPlanner 8/8 abstain (correct) | local model disqualified; Spark 1-call-valid on hardware exists (G3 attempt 4, different case) |
| NL parse, 8 hard prompts (N4) | llama 2/8 resolved incl. 1 wrong-skill (tv_volume_step for pause) | keyword fallback: safe clarify | Spark (4 calls) abstains on unregistered skills — safety gain, not just quality |
| STT→parse, 16 noisy transcripts (N2b) | MMS-1B STT (Meta) | parser: 16/16 no wrong-skill | errors become honest clarifications, never wrong skills |
| Concurrency (S1 claim) | n/a | 2-thread race → 1 effect, 1 txn (probe green) | deterministic win, no model needed |
| UI draft mechanics (S2/C1) | prompt builder (runtime) | slots+refusals+kernel-schema conformance, 10 tests | mechanics proven; model wording unmeasured |
| Plan validation (S3/S3b) | emitter (runtime) | DAG/consent/verify/cycle checks + obv4.1-wf conformance, 10 tests | mechanics proven; Meta-authored plans unmeasured |
| Latency (this box) | llama synth ~21 s; Spark 4–12 s/call | parse keyword <1 s; poll 48 ms | local models too slow for interactive synthesis |
| Cost | $1.30 reserved / ~$0.11 estimated total | $0 | every cent receipted in canonical ledger |

Unmeasured by design (awaiting seal/owner): held-out novelty, Meta-authored
UI wording quality, Meta-authored multi-device plans on hardware.
