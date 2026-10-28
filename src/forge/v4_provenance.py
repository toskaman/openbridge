"""V4 ModelRunProvenance + ProofEmitter. Identifiers redacted; receipts need read-back."""
import re

from src.forge import v4_schemas as S

SENSITIVE_KEYS = {'contact', 'phone', 'number', 'mac', 'address', 'ip'}
DIGITS = re.compile(r'\+?\d[\d .()-]{6,}\d')


def _scrub(value):
    if isinstance(value, dict):
        return {k: (S.opaque('pii', str(v)) if k in SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return DIGITS.sub('[redacted-digits]', value)
    return value


def record(model_family, version, endpoint, local, run_id, task, evidence_ids,
           registry_version, manifest_hashes, usage, latency_ms, **extra):
    rec = {'schema_version': S.SCHEMA_VERSION, 'model_family': model_family, 'version': version,
           'endpoint': 'local' if local else 'hosted:' + S.opaque('endpoint', endpoint),
           'local': bool(local), 'run_id': run_id, 'task': task,
           'evidence_ids': list(evidence_ids), 'registry_version': registry_version,
           'manifest_hashes': list(manifest_hashes), 'usage': dict(usage),
           'latency_ms': latency_ms}
    rec.update(_scrub(dict(extra)))
    return rec


class ProofError(ValueError):
    pass


def emit(stages):
    need = ('candidate_digest', 'validator', 'sandbox', 'owner_approval', 'deployment', 'readback')
    if any(stages.get(k) is None for k in need):
        raise ProofError('READBACK_REQUIRED_OR_INCONCLUSIVE')
    receipt = {'schema_version': S.SCHEMA_VERSION, 'receipt_id': 'r-pending'}
    receipt.update({k: stages[k] for k in need})
    receipt['receipt_id'] = 'r-' + S.digest({k: v for k, v in receipt.items() if k != 'receipt_id'})[:16]
    return receipt
