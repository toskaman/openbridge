# Meta capability planner

Primary local model: muse-glimmer:30b-q4_K_M. Pinned manifest digest: de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1. Comparison model: llama3.2:3b-instruct-q4_K_M, digest a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72. Both use the existing project broker and check catalog identity before and after a request. No cloud fallback, automatic retry or external provider charge occurs.

The planner sees only opaque capability/relay IDs, source simulation flags, operations and evidence references from deterministically eligible candidates. It does not receive raw addresses, advertised names, manufacturer payloads, credentials or the whole device graph. The owner goal is fixed to expose_remote_ble_observations in v1.

The model returns only a JSON plan: goal, decision, steps, evidence_refs and requires_consent=true. A complete valid proposal has exactly two steps: an existing eligible capability read_observations, then pc.virtual_api.publish/publish_readonly. Evidence must exactly match the selected capability. Unknown IDs, reversed transitions, extra commands, invented evidence or consent waiver are rejected. Unavailable is valid only when no candidate exists.

The current design deliberately lets rules make safety and eligibility decisions. This may leave little measured advantage to a model on the narrow task. The benchmark reports this rather than claiming superior reasoning. Interpretive explanation and larger compositional goals need separate future evidence.

Attribution: Built with Llama and Meta Muse Glimmer. Actual usage, latencies, tokens and costs are recorded in benchmark JSON when executed. A configured model is not a successful inference proof. Hosted Spark is excluded from this run without fresh free-credit verification. The previously supplied balance must not be silently refreshed.
