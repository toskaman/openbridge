# Discriminated Meta result type (Campaign Two S4.7)

Every Meta model reply is exactly one of three outcomes, validated in
`src/forge/meta_result.py`:

- `proposal` -- carries an installable/executable payload (a UI patch, a
  plan's steps) checked by the caller's own deterministic validator. Only
  this outcome ever yields something the system may act on.
- `clarification` -- carries one `clarifying_question`. Yields nothing.
- `refusal` -- carries a human-readable `reason` plus an optional
  machine-readable `code`. Yields nothing.

A refusal or clarification that smuggles a payload is rejected as a whole,
so a generated interface can always refuse instead of emitting a panel or
a plan, and can never emit a misleading substitute "to be helpful" (the
S5-T3 pathology).

## Refusal codes

`SHELL_NOT_OFFERED`, `UNKNOWN_DEVICE`, `UNAUTHORIZED_DEVICE`,
`OFF_MANIFEST_CAPABILITY`, `APPROVAL_EVASION`,
`IRREVERSIBLE_WITHOUT_CONSENT`, `UNSUPPORTED`. Unknown codes reject the
reply. The code is surfaced by `dashboards propose` when present.

## Consumers

- UI panels: `src/forge/v4_ui.py` (`parse_response` keeps its 3-tuple for
  the frozen S5-T3 harness; `parse_response_full` adds the code).
- Workflow plans: `src/runtime/nl_plan.py` accepts the envelope and keeps
  accepting bare `{"steps": [...]}` replies; `plan-text` constrains the
  model to the envelope schema.

## Compatibility

Frozen S12 spellings (`needs_clarification`, `unsupported`) still parse
and are canonicalized, so historical evidence records read verbatim. The
S5-T3 failed evaluations (`docs/evidence/s5-t3-*`) and harness
(`dev/s5_t3_offline.py`) are preserved untouched for comparison.

## Tests

- `tests/forge/test_meta_result.py` -- the type itself.
- `tests/forge/test_model_refusal.py` -- UI outcomes incl. codes/aliases.
- `tests/runtime/test_nl_refusal.py` -- NL envelope plus the six
  malicious/unsupported categories: arbitrary shell controls, nonexistent
  devices, off-manifest capabilities, approval evasion, unauthorized
  devices, irreversible settings without consent.
