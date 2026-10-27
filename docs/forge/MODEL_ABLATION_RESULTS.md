# Forge model ablation results

This report below is the frozen **v1** evaluation. Subsequent CPU-only execution completed inference, and a separate schema-constrained v2 proposal and live browser lifecycle passed on synthetic data. Earlier failed attempts remain preserved. V2 moves impossible-case decisions to rules and limits output transitions, so these smoke tests are not replacement benchmark scores or evidence of superior reasoning. See META_CAPABILITY_PLANNER.md and live-glimmer-browser-receipt.json. No held-out v2 accuracy is claimed yet.

Frozen dataset: 64 synthetic scenarios across 16 categories; 48 development and 16 held-out variants. SHA256: d3d3eeb1eb591eba15e2a7e4166efd68e244eb2b57f191aed871246f59210802. Dataset committed in d9a3666 before these model runs. No prompt tuning followed the scores. Held-out means not presented to models during prompt design; the author generated both splits, so this is not an independently authored blind evaluation.

| Route | Scored cases | Accepted exact plans | Correct validated refusals | Provider cost |
|---|---:|---:|---:|---:|
| Rules | 64 | 100% | 100% | $0 |
| Llama 3B | 64 | 0% | 0% | $0 |
| Muse Glimmer | 0 | Unavailable | Unavailable | $0 |
| Muse Spark | 0 | Not run | Not run | $0 |

Llama's raw decision labels matched 44/64 cases: all 44 impossible cases were labeled unavailable. However, those responses included invalid non-empty evidence references, so none qualified as a complete validated refusal. All 20 feasible cases were also refused. 63 responses were captured as JSON; one call failed before an accepted JSON result. Median latency was 4331 ms; 11,016 input and 3,976 output tokens were observed. Exact model identity and 2,330,848,131 model-resident bytes with zero VRAM are recorded per case. These memory numbers are the local service's model size, not total process RSS. Python peak allocated bytes are separately measured with tracemalloc.

Glimmer was catalog-visible with the correct digest, but two actual synthetic attempts failed during model startup with host-memory allocation errors. A third, CPU-only constrained diagnostic failed loading the projector. Its 64-case batch was not started after that repeated resource failure. No output, speed, accuracy or bonus eligibility is inferred from a loaded catalog entry. Existing other model services were not changed. Spark was not called because this run had no fresh verified promotional-credit observation.

Zero unknown capability IDs and zero proposed permission violations were observed in the Llama plans that returned JSON; failed/absent responses are not evidence of safe reasoning. Rules first filter eligibility, so this is a constrained gate-and-selection ablation, not an unrestricted safety benchmark. The fixed two-step scope does not demonstrate arbitrary compositional reasoning, discovery of new integrations, cloud/local tradeoff reasoning, or Undo-capable planning. Such goals remain unavailable.

The prior project agent benchmark remains unchanged: rules 90%, Glimmer 86.7%, Llama 3B 53.3% over 30 cases repeated three times. Different task and scoring: do not compare the percentages as an improvement curve.

Decision: retain deterministic rules for this publication task. Local Meta remains an optional, validated proposal route with explicit failure states. No intelligence advantage is claimed. Raw current results: benchmark-rules.json, benchmark-llama3b.json, benchmark-glimmer.json. Separate UX evidence: meta-ux-review-receipt.json records a successful actual local Llama review; it is not a planning score.
