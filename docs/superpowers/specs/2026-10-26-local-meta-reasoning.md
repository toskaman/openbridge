# Private local Meta reasoning

Add explicit opt-in local reasoning with Meta Llama 3.2 3B, using the preparation guide's fixed llama3.2:3b-instruct-q4_K_M tag. Pin the official registry manifest digest a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72. Verify that digest in the local model catalog before every call; unknown or retagged models fail closed.

Use a separate loopback Ollama service on port 11437 with a private model directory, stripped credential environment, CPU-only configuration and one model/one inference at a time. Leave the user's existing local model service untouched. Model weights stay outside Git. Download is about 2 GB from the official registry; no paid provider is involved. Explicit request options set num_gpu=0, num_thread=4, num_ctx=2048 and bounded output.

The existing application still starts without inference by default. A --local-meta startup option enables this configured local provider. There is no automatic cloud fallback. Cloud Muse Spark retains its supervised free-credit guard and may never receive physical-device facts through this route.

Local reasoning can review a current authorized Android read-only report using only allowlisted non-identifying numeric facts, independently reread by the server. It cannot execute an action. Output remains English and schema-validated: summary, existing evidence references, inspect_only action and uncertainty. Preserve source labels and reject unsupported model identity, invalid schema or invented numeric claims.

Tests precede implementation: digest, endpoint, privacy allowlist, schema, source routing, one in-flight request and no cloud fallback. Record an actual model/digest/token/latency trace if a controlled local call succeeds. No physical setting write or additional cloud inference is required. Publish exact Meta usage and a Built with Llama attribution on GitHub and in the local-provider UI.
