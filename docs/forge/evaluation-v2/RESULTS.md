# Frozen v2 results — 27 October 2026

All fixtures are synthetic. Cases and gold labels were frozen before inference. The unchanged planner supports one observation read followed by local read-only publication. These results do not measure unfamiliar-protocol learning, arbitrary composition or V7 failover intelligence.

| Route | Total correct | Actual model calls / successful proposals | Development | Heldout | Median actual call | Input/output tokens | Provider cost |
|---|---|---|---|---|---|---|---|
| rules | 80/80 | 0 / 0 | 40/40; 0/0 model proposals | 40/40; 0/0 model proposals | None ms | 0/0 | $0 |
| llama | 80/80 | 25 / 25 | 40/40; 12/12 model proposals | 40/40; 13/13 model proposals | 8647 ms | 6560/2298 | $0 |
| glimmer | 80/80 | 25 / 25 | 40/40; 12/12 model proposals | 40/40; 13/13 model proposals | 76061 ms | 6635/2005 | $0 |

Each route includes 45 deterministic source/policy refusals, 10 separate harness scope refusals and 25 eligible proposal cases. Rules generate those 25 plans without inference; Llama and Glimmer each made 25 local model calls. The model routes have no measured accuracy advantage here. Zero hallucinated IDs or proposed permission violations were observed in these receipts; deterministic gates remain responsible for authorization.

Llama and Glimmer receipts retain exact source hashes, raw plans, errors, tokens and per-case latency. They were collected from the frozen fdf9922-era source; the final Rules run uses the same recorded component hashes. No prompt or label tuning followed these results. Original v1 outcomes remain unchanged.

Memory: per-case Python tracemalloc allocations and Ollama loaded-size metadata are not process peak RSS. The separate Windows memory snapshot is a point-in-time working-set observation, not a peak or a sum of unique physical pages. Local $0 provider cost excludes hardware/electricity. The initial model-state receipt and Llama load-release receipt document only these runs. Glimmer used a five-minute keep-alive; no later global model unload was performed because other contributors may now be using that service.

Raw receipts: [Rules](results/rules.json), [Llama](results/llama.json), [Glimmer](results/glimmer.json), [memory snapshot](results/glimmer-memory-snapshot.json). No fresh inference was made to publish this report.
