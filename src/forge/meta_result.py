"""Campaign Two S4.7: discriminated Meta result type.

Every Meta model reply is exactly one of three outcomes -- Proposal |
Clarification | Refusal -- and each outcome is explicitly validated here,
in one shared place, instead of per-caller ad-hoc checks:

- Proposal carries an installable/executable payload (a UI patch, a plan's
  steps) that is validated by the caller's own deterministic validator.
  Only this outcome ever yields something the system may act on.
- Clarification carries a single clarifying question. It yields nothing
  installable or executable; the caller surfaces the question instead.
- Refusal carries a human-readable reason plus an optional machine-readable
  refusal code. It yields nothing installable or executable.

A generated interface is therefore always allowed to refuse instead of
emitting a panel or a plan: refusal is a first-class, validated outcome,
not a parse accident. Conversely a refusal or clarification that smuggles
a payload is rejected as a whole (the S5-T3 pathology -- a misleading
substitute emitted "to be helpful" -- must never validate).

Legacy S12 wire spellings (needs_clarification, unsupported) are accepted
on input and canonicalized, so frozen evidence records keep parsing
verbatim; new prompts and callers use the three canonical names.
"""

PROPOSAL = 'proposal'
CLARIFICATION = 'clarification'
REFUSAL = 'refusal'
OUTCOMES = (PROPOSAL, CLARIFICATION, REFUSAL)

# Frozen S12 spellings still accepted on input (canonicalized on output).
LEGACY_ALIASES = {'needs_clarification': CLARIFICATION,
                  'unsupported': REFUSAL}

MAX_DETAIL_CHARS = 500

# Machine-readable refusal codes (optional on refusal; unknown codes are
# rejected -- a code the system does not know is not a valid refusal).
SHELL_NOT_OFFERED = 'SHELL_NOT_OFFERED'
UNKNOWN_DEVICE = 'UNKNOWN_DEVICE'
UNAUTHORIZED_DEVICE = 'UNAUTHORIZED_DEVICE'
OFF_MANIFEST_CAPABILITY = 'OFF_MANIFEST_CAPABILITY'
APPROVAL_EVASION = 'APPROVAL_EVASION'
IRREVERSIBLE_WITHOUT_CONSENT = 'IRREVERSIBLE_WITHOUT_CONSENT'
UNSUPPORTED = 'UNSUPPORTED'
REFUSAL_CODES = frozenset({SHELL_NOT_OFFERED, UNKNOWN_DEVICE,
                           UNAUTHORIZED_DEVICE, OFF_MANIFEST_CAPABILITY,
                           APPROVAL_EVASION, IRREVERSIBLE_WITHOUT_CONSENT,
                           UNSUPPORTED})

ENVELOPE_KEYS = {'outcome', 'reason', 'code', 'clarifying_question'}


class MetaError(ValueError):
    pass


def canonical_outcome(value):
    """Map a raw outcome discriminant to its canonical name."""
    if not isinstance(value, str):
        raise MetaError('RESPONSE_OUTCOME: %r' % (value,))
    if value in OUTCOMES:
        return value
    if value in LEGACY_ALIASES:
        return LEGACY_ALIASES[value]
    raise MetaError('RESPONSE_OUTCOME: %r' % (value,))


def _detail(value, key):
    text = value.get(key) or ''
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_DETAIL_CHARS:
        raise MetaError('RESPONSE_DETAIL')
    return text.strip()


def parse(value, payload_key, validate_payload):
    """Split a model reply into (outcome, payload|None, detail, code|None).

    value must be a dict holding the 'outcome' discriminant. Proposal
    requires payload_key and validates it through validate_payload (whose
    errors propagate unchanged); clarification and refusal must NOT carry
    the payload key at all and require their own detail text. Unknown keys
    or outcomes reject the whole reply. Only outcome == 'proposal' yields
    a payload; every other outcome yields None (nothing installable,
    nothing executable).
    """
    allowed = set(ENVELOPE_KEYS) | {payload_key}
    if not isinstance(value, dict) or set(value) - allowed or 'outcome' not in value:
        raise MetaError('RESPONSE_SHAPE')
    outcome = canonical_outcome(value['outcome'])
    if outcome == PROPOSAL:
        if payload_key not in value:
            raise MetaError('RESPONSE_PAYLOAD_MISSING')
        return outcome, validate_payload(value[payload_key]), '', None
    if payload_key in value:
        raise MetaError('RESPONSE_%s_WITH_%s' % (payload_key.upper(), outcome.upper()))
    if outcome == REFUSAL:
        code = value.get('code')
        if code is not None and code not in REFUSAL_CODES:
            raise MetaError('RESPONSE_CODE: %r' % (code,))
        return outcome, None, _detail(value, 'reason'), code
    return outcome, None, _detail(value, 'clarifying_question'), None
