"""Command Center P0: versioned, typed user-intent contract (French/English).

An intent is a validated document, never a shell string. Lifecycle:
draft -> resolved | needs_clarification | unsupported | escalation_required
resolved -> approved | rejected; approved -> executed | failed.
The deterministic executor only accepts approved intents whose skill contract
validates; the model can never authorize its own privileged actions.
"""
import re
import secrets

INTENT_VERSION = 1
LANGS = ('en', 'fr')
RISK = ('low', 'medium', 'high')
STATUS = ('draft', 'resolved', 'needs_clarification', 'unsupported',
          'escalation_required', 'approved', 'rejected', 'executed', 'failed')
TARGET_KINDS = ('device', 'group', 'category', 'room', 'originator')
_INTENT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,199}$')

_FIELDS = {'intent_id', 'version', 'raw_text', 'lang', 'outcome', 'targets',
           'skill_id', 'params', 'confidence', 'ambiguities',
           'clarifying_question', 'risk_level', 'status', 'provenance'}


class IntentError(ValueError):
    pass


def new_intent(raw_text, lang):
    if lang not in LANGS:
        raise IntentError(f'lang must be one of {LANGS}')
    if not isinstance(raw_text, str) or not raw_text.strip() or len(raw_text) > 2000:
        raise IntentError('raw_text must be 1..2000 characters')
    return {'intent_id': 'int-' + secrets.token_hex(8), 'version': INTENT_VERSION,
            'raw_text': raw_text.strip(), 'lang': lang, 'outcome': None,
            'targets': [], 'skill_id': None, 'params': {}, 'confidence': None,
            'ambiguities': [], 'clarifying_question': None, 'risk_level': 'low',
            'status': 'draft', 'provenance': {'parser': 'rules', 'model_id': None}}


def validate_intent(doc):
    """Return a list of 'path: problem' strings (empty when valid)."""
    if not isinstance(doc, dict):
        return ['$: must be an object']
    errs = [f'$.{k}: unexpected field' for k in doc if k not in _FIELDS]
    if doc.get('version') != INTENT_VERSION:
        errs.append('$.version: must be 1')
    rt = doc.get('raw_text')
    if not isinstance(rt, str) or not rt.strip() or len(rt) > 2000:
        errs.append('$.raw_text: must be 1..2000 characters')
    if doc.get('lang') not in LANGS:
        errs.append(f'$.lang: must be one of {LANGS}')
    if doc.get('risk_level') not in RISK:
        errs.append(f'$.risk_level: must be one of {RISK}')
    status = doc.get('status')
    if status not in STATUS:
        errs.append(f'$.status: must be one of {STATUS}')
    conf = doc.get('confidence')
    if conf is not None and (not isinstance(conf, (int, float)) or isinstance(conf, bool)
                             or not 0.0 <= conf <= 1.0):
        errs.append('$.confidence: must be null or 0..1')
    tg = doc.get('targets')
    if not isinstance(tg, list) or len(tg) > 32:
        errs.append('$.targets: must be a list of at most 32')
    else:
        for i, t in enumerate(tg):
            if (not isinstance(t, dict) or set(t) != {'kind', 'ref'}
                    or t.get('kind') not in TARGET_KINDS
                    or not isinstance(t.get('ref'), str) or not _INTENT_RE.match(t['ref'])):
                errs.append(f'$.targets[{i}]: must be {{kind, ref}} with a safe ref')
    if not isinstance(doc.get('params'), dict) or len(doc['params']) > 32:
        errs.append('$.params: must be an object of at most 32 entries')
    if not isinstance(doc.get('ambiguities'), list) or any(not isinstance(a, str) for a in doc['ambiguities']):
        errs.append('$.ambiguities: must be a string list')
    prov = doc.get('provenance')
    if (not isinstance(prov, dict) or set(prov) != {'parser', 'model_id'}
            or prov.get('parser') not in ('rules', 'local', 'cloud')
            or (prov.get('model_id') is not None and not isinstance(prov['model_id'], str))):
        errs.append('$.provenance: must be {parser: rules|local|cloud, model_id: str|null}')
    if status == 'resolved':
        if not doc.get('skill_id') or not doc.get('outcome') or doc.get('confidence') is None:
            errs.append('$.status: resolved needs skill_id, outcome and confidence')
        if not tg:
            errs.append('$.status: resolved needs at least one target')
    if status == 'needs_clarification' and not doc.get('clarifying_question'):
        errs.append('$.status: needs_clarification needs clarifying_question')
    return errs
