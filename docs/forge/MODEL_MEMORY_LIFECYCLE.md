# Explicit local planner memory lifecycle

Implemented in local_models.py, planner_v2.py, demo_host.py and the Forge UI. Prepare/release routes accept only `{}`, share the planner lock and use the exact isolated Meta model. The UI does not reread a provider during these controls and requires refreshed observations after preparation.

Actual default-loading experiment: model-memory-receipt.json records preload failure from host-memory allocation while loading the vision component. Cleanup succeeded and the model list was empty afterward. This failure is retained.

The separate memory-mapped experiment, model-memory-mmap-receipt.json, succeeded: preparation 49,595 ms; fresh synthetic plan 51,686 ms; release 191 ms; no resident model afterward. The service reported model size 12,521,161,356 bytes and zero VRAM. This is not process RSS or a general performance benchmark. Provider cost was $0. The isolated adapter now explicitly requests use_mmap=true, supported by the primary [Ollama runner options](https://github.com/ollama/ollama/blob/main/api/types.go). Model weights and digest remain unchanged.

Service removal stays available during a pending plan, prepare or release operation. The late result cannot recreate the service, reenable publication or overwrite the owner's removal confirmation. An in-flight model operation may finish; its result grants no authority. Releasing the local model remains a separate explicit action.

Owner constraint remains active: no video generation until the complete project is finished.

Problem: observed CPU planner calls spend a large part of their 78–98 seconds loading weights. Loading after collecting observations can exhaust their freshness window. Preparing a model must not collect device evidence or imply permission.

Design: explicit Prepare local planner and Release planner memory controls. The already configured isolated Meta route sends an empty chat request for the exact pinned model, with bounded five-minute idle retention or immediate release. No prompt, facts, arbitrary model, endpoint or generated code is accepted. Validate model identity, load/unload state and absence of generated tokens. Share the planner lock so prepare/release cannot queue behind a plan in the same host.

The HTTP routes require the existing bearer/Origin/Host protections and an exact empty JSON object. The default no-model host and unsupported brokers hide these controls. Source availability and publication remain independent: prepare never refreshes source data; releasing memory never changes a device or revokes its relay.

The UI reports preparation/release confirmation or failure. It does not claim memory was released after an ambiguous failure. Tests use controlled transports and browsers before any actual model-memory experiment. Any performance receipt must separately report loading and subsequent planning time rather than retroactively changing earlier scores.

Primary behavior reference: https://docs.ollama.com/faq (empty requests preload; keep_alive bounds retention and zero releases a model).
