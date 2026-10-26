# Safety and model boundaries

Phase 1 calls no inference model. The ai package is an empty boundary, not a working model integration. Do not claim runtime compliance proof from an unused model registry.

Future model integration must pin actual Meta deployments, verify identity, sanitize inputs and record real traces. Unknown models and opaque fallbacks must fail closed. Model advice must never execute commands directly. Each physical write requires authorized scope, an exact snapshot, deterministic checks and independent read-back and rollback verification.

No credentials, serial numbers, network identifiers or device dumps belong in public evidence. Current fixtures contain only synthetic values.
