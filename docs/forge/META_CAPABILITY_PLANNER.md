# Meta capability planner

## Subsequent experimental v2 proof

The original v1 planner and frozen unfavorable results remain unchanged. The separate SchemaConstrainedPlanner decides impossible cases with rules without calling a model. For eligible candidates, Muse Glimmer returns the complete JSON proposal. Its schema limits step arrays to approved read/publish transitions; the independent validator still checks evidence coupling, consent and freshness after inference. Invalid outputs are rejected, never repaired into claimed model success. Non-string enum support is covered by the primary [llama.cpp grammar tests](https://github.com/ggml-org/llama.cpp/blob/master/tests/test-json-schema-to-grammar.cpp).

A separate foreground service on port 11439 hides GPUs at startup and uses the existing pinned weights with an environment limited to required OS settings. It loaded Glimmer successfully, unlike the earlier mixed GPU/projector attempts. The first CPU v1 inference returned an incorrect refusal; an early v2 output targeted publication on the relay and was rejected. Those receipts remain intact.

The constrained v2 smoke then passed: glimmer-v2-constrained-proposal-receipt.json records 218 input / 67 output tokens, 80,276 ms including load, model-resident size 17,078,765,483 bytes, observed VRAM 0, and provider cost $0. live-glimmer-browser-receipt.json separately proves an actual browser-to-Glimmer call followed by owner consent, publication, HTTP read and removal on synthetic data, with no JavaScript errors. These are development proofs, not held-out accuracy, physical orchestration or an intelligence advantage.

Optional startup: run `python -m dev.forge_glimmer_cpu_service` in its own foreground terminal, then `python -m src.forge.demo_host --glimmer-cpu-v2`. No download or cloud fallback occurs. Other services are untouched. The review regression test rejects evidence that expires during inference using monotonic elapsed time; publication independently rereads the provider.

Primary local model: muse-glimmer:30b-q4_K_M. Pinned manifest digest: de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1. Comparison model: llama3.2:3b-instruct-q4_K_M, digest a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72. Both use the existing project broker and check catalog identity before and after a request. No cloud fallback, automatic retry or external provider charge occurs.

The planner sees only opaque capability/relay IDs, source simulation flags, operations and evidence references from deterministically eligible candidates. It does not receive raw addresses, advertised names, manufacturer payloads, credentials or the whole device graph. The owner goal is fixed to expose_remote_ble_observations in v1.

The model returns only a JSON plan: goal, decision, steps, evidence_refs and requires_consent=true. A complete valid proposal has exactly two steps: an existing eligible capability read_observations, then pc.virtual_api.publish/publish_readonly. Evidence must exactly match the selected capability. Unknown IDs, reversed transitions, extra commands, invented evidence or consent waiver are rejected. Unavailable is valid only when no candidate exists.

The current design deliberately lets rules make safety and eligibility decisions. This may leave little measured advantage to a model on the narrow task. The benchmark reports this rather than claiming superior reasoning. Interpretive explanation and larger compositional goals need separate future evidence.

Attribution: Built with Llama and Meta Muse Glimmer. Actual usage, latencies, tokens and costs are recorded in benchmark JSON when executed. A configured model is not a successful inference proof. Hosted Spark is excluded from this run without fresh free-credit verification. The previously supplied balance must not be silently refreshed.
