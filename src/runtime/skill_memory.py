"""§7.5 instant reuse + §7.4 lifecycle slice for Meta-composed skills.

First request: Meta proposes, OpenBridge validates, the owner approves,
execution verifies, the record is saved PROPOSED then marked READY.
Repeat request: lookup hits the READY record with zero model tokens.

Lookup NEVER authorizes: the caller must still run fresh device-liveness
checks, consent, approve and execute. Persistence is single-writer through
StateStore (same owner-driven flow as the rest of P0).
"""
import re

from src.runtime import skills as S

STATES = ('PROPOSED', 'READY', 'DISABLED', 'REVOKED')
_REQUIRED = ('skill_id', 'targets', 'params', 'capability_ids', 'provenance')


class SkillMemoryError(ValueError):
    pass


def normalize(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


class Memory:
    def __init__(self, store=None):
        self._store = store
        self._mem = {}

    def _all(self):
        if self._store is None:
            return self._mem
        data = self._store.load()
        skills = data.get('saved_skills', {})
        if not isinstance(skills, dict):
            raise SkillMemoryError('saved_skills state is corrupt; refusing to guess')
        return skills

    def _put(self, key, record):
        if self._store is None:
            self._mem[key] = record
            return
        skills = dict(self._all())
        skills[key] = record
        self._store.update(saved_skills=skills)

    def save(self, text, record):
        """Store a validated composition as PROPOSED (not reusable yet)."""
        key = normalize(text)
        if not key:
            raise SkillMemoryError('empty request text')
        if not isinstance(record, dict) or any(k not in record for k in _REQUIRED):
            raise SkillMemoryError('record must carry skill_id, targets, params, capability_ids, provenance')
        try:
            S.resolve(record['skill_id'], record['params'] or {})
        except S.SkillError as e:
            raise SkillMemoryError(f'not a resolvable skill: {e}') from None
        if record['skill_id'] not in (record['capability_ids'] or []):
            raise SkillMemoryError('capability_ids must retain the composed skill')
        self._put(key, {**record, 'state': 'PROPOSED', 'request': key})
        return key

    def mark_ready(self, text):
        self._transition(text, ('PROPOSED',), 'READY')

    def disable(self, text):
        self._transition(text, ('READY',), 'DISABLED')

    def enable(self, text):
        self._transition(text, ('DISABLED',), 'READY')

    def revoke(self, text):
        key = normalize(text)
        if key not in self._all():
            raise SkillMemoryError('unknown saved skill')
        rec = dict(self._all()[key])
        rec['state'] = 'REVOKED'
        self._put(key, rec)

    def _transition(self, text, allowed, new):
        key = normalize(text)
        rec = self._all().get(key)
        if rec is None:
            raise SkillMemoryError('unknown saved skill')
        if rec.get('state') not in allowed:
            raise SkillMemoryError(f"cannot move {rec.get('state')} to {new}")
        self._put(key, {**rec, 'state': new})

    def lookup(self, text):
        """Return the READY record for an exact normalized repeat, else None.

        A hit replays the validated composition without model tokens; the
        caller still owes liveness, consent, approve and execute.
        """
        rec = self._all().get(normalize(text))
        if rec is None or rec.get('state') != 'READY':
            return None
        return dict(rec)


def to_intent(record, raw_text, lang='en'):
    """Rebuild a validator-clean resolved intent from a READY record.

    Provenance is honest: parser='local' (deterministic memory replay),
    model_id=None (the model did NOT parse this request). The record keeps
    the original model provenance. Risk level is re-derived fresh from the
    live skill registry, never trusted from memory.
    """
    from src.runtime import intent as I
    if record.get('state') != 'READY':
        raise SkillMemoryError('only READY records replay')
    return {'version': I.INTENT_VERSION, 'raw_text': raw_text, 'lang': lang,
            'risk_level': S.get(record['skill_id'])['risk_level'],
            'status': 'resolved', 'skill_id': record['skill_id'],
            'outcome': 'replay:' + normalize(raw_text),
            'confidence': 1.0, 'targets': record['targets'],
            'params': record['params'], 'ambiguities': [],
            'clarifying_question': None,
            'provenance': {'parser': 'local', 'model_id': None}}
