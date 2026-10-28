"""V4 EvidenceResolver: read-only, sanitized, provenance-bound device facts."""
from src.forge import v4_schemas as S

KNOWN_CATEGORIES = {'phone', 'tv', 'vacuum', 'watch', 'computer', 'media', 'android'}


class EvidenceError(ValueError):
    pass


def registry_digest(skills, primitives):
    norm = {'skills': sorted([dict(sorted(s.items())) for s in skills],
                             key=lambda d: d.get('skill_id', '')),
            'primitives': sorted(primitives)}
    return S.digest(norm)


def resolve(devices, relays, primitive_ids, now):
    out_devices = []
    for i, d in enumerate(devices):
        cat = d.get('category')
        if cat not in KNOWN_CATEGORIES:
            raise EvidenceError('UNKNOWN_DEVICE_CATEGORY')
        facts = []
        for j, f in enumerate(d.get('facts', [])):
            raw = f.get('value')
            quarantined = isinstance(raw, str) and bool(S.SUSPICIOUS.search(raw))
            facts.append({'fact_id': 'f-%d-%d' % (i, j), 'kind': str(f.get('kind', 'unknown'))[:32],
                          'value_class': 'quarantined_text' if quarantined else 'observed_value',
                          'source': str(f.get('source', 'unknown'))[:32],
                          'observed_at': float(f.get('observed_at', now)),
                          'evidence_ref': S.opaque('fact', '%s|%s|%s' % (d.get('device_id', i), f.get('kind'), j))})
        out_devices.append({'opaque_id': S.opaque('device', str(d.get('device_id', 'dev-%d' % i))),
                            'category': cat, 'permission_scope': list(d.get('permission_scope', ['observe'])),
                            'facts': facts})
    body = {'schema_version': S.SCHEMA_VERSION, 'bundle_id': 'b-pending', 'observed_at': float(now),
            'devices': out_devices, 'relays': [{'opaque_id': S.opaque('relay', str(r))} for r in relays],
            'primitives': sorted(primitive_ids), 'registry_digest': ''}
    body['bundle_id'] = 'b-' + S.digest({k: v for k, v in body.items() if k != 'bundle_id'})[:16]
    return S.validate_bundle(body)
