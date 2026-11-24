# Verifiable device agent

Loop: OBSERVE (ADB read-only facts + allowlisted optional apps actually installed, with exact state) -> META PLAN (pinned local Llama 3.2 3B, schema-constrained: inspect_only or disable_optional_app on one eligible candidate) -> deterministic GATE (NO_ACTION / DENY / REVIEW_REQUIRED; absent proof => DENY) -> explicit owner CONSENT -> ACT through the durable transaction engine -> independent READ-BACK -> exact UNDO.

The owner goal is a fixed enum (review, declutter); there is no free-text prompt path. The model never sees identifiers. Plans are rejected when they name an ineligible package, reference unknown evidence, invent numbers, omit referenced values or fail to name the proposed app. Model output cannot execute anything; only the gate-approved, consented plan reaches the engine. Server opt-in: `--local-meta --agent`. Without it the routes return 409.
