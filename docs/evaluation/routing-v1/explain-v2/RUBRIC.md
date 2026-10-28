# Frozen citation rubric (routing-v1 explanations) — DRAFT until owner-approved freeze

Each explanation reply is graded sentence by sentence by a deterministic checker
plus one human pass. Labels per sentence: SUPPORTED, UNSUPPORTED, INVALID.

- SUPPORTED: the sentence carries a `[field]` citation and the cited field exists
  in the sampled row with a value that entails the sentence.
- UNSUPPORTED: no citation, a citation to an absent field, or a claim the field
  value does not entail (including cross-case comparisons and quality judgments
  such as "better", "robust", "correct" beyond `predictions.router == expected`).
- INVALID (whole reply): wrong section structure (not exactly DECISION/EVIDENCE/
  LIMITS), non-JSON-safe control output, or more than 800 completion tokens.

Reported per call: counts of SUPPORTED/UNSUPPORTED, INVALID flag, exact model
string returned by the API, prompt/completion tokens, estimated cost, request id.
Aggregate reported: totals only, never a quality score for the router. All
replies, including INVALID ones, are retained verbatim. Disagreements between
the deterministic checker and the human pass are reported as DISPUTED with both
labels kept; DISPUTED never resolves to SUPPORTED silently.
