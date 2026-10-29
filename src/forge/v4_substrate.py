"""V4 Muse->substrate wiring: build obv4.1 documents, compile-first, surface rejects.

The substrate object is duck-typed (compile/validate/manifest_hash + error.code):
the substrate PR is unmerged, so this module never imports it. Integration is
proven by the shared contract version + the plan_hash recomputation check.
"""
import sys

from src.forge import v4_schemas as S

CONTRACT_VERSION = 'obv4.1'


class WireError(ValueError):
    pass


def _resolve(substrate, name):
    """Instance attr -> class attr -> defining-module attr (the real kernel
    exposes CONTRACT_VERSION/manifest_hash at module scope)."""
    value = getattr(substrate, name, None)
    if value is not None:
        return value
    value = getattr(type(substrate), name, None)
    if value is not None:
        return value
    module = sys.modules.get(type(substrate).__module__)
    return getattr(module, name, None) if module is not None else None


def contract_version(substrate):
    return _resolve(substrate, 'CONTRACT_VERSION')


def hash_fn(substrate):
    fn = _resolve(substrate, 'manifest_hash')
    if not callable(fn):
        raise WireError('NO_HASH_FN')
    return fn


def to_manifest(candidate, target, model_run, title, permissions, facts_required,
                expires_at, max_fact_age_s=600, inputs=None, evidence_extra=()):
    steps = []
    for i, s in enumerate(candidate['primitive_chain']):
        steps.append({'step_id': 's%d' % i, 'primitive_id': s['primitive_id'],
                      'args': dict(s['input']), 'on_uncertain': 'INCONCLUSIVE'})
    return {'capability_id': candidate['candidate_id'],
            'evidence_refs': list(candidate['evidence_refs']) + list(evidence_extra),
            'expires_at': expires_at, 'facts_required': list(facts_required),
            'inputs': dict(inputs or {}), 'manifest_version': CONTRACT_VERSION,
            'max_fact_age_s': int(max_fact_age_s),
            'model_run': {'model': model_run['model'], 'provider': 'meta', 'run_id': model_run['run_id']},
            'origin': 'meta_generated', 'permissions_requested': list(permissions),
            'steps': steps, 'target': {'category': target['category'],
                                       'device_fingerprint': target['device_fingerprint']},
            'title': title}


def compile_first(substrate, manifest, facts):
    if contract_version(substrate) != CONTRACT_VERSION:
        raise WireError('CONTRACT_MISMATCH')
    try:
        compiled = substrate.compile(manifest, facts)
    except Exception as e:  # noqa: BLE001 - every substrate refusal maps to a status
        code = getattr(e, 'code', 'UNKNOWN')
        if code == 'REJECTED_UNSUPPORTED_PRIMITIVE':
            return {'status': 'NO_SUPPORTED_PRIMITIVE',
                    'engineering_request': getattr(e, 'extra', {}).get('engineering_request')}
        return {'status': 'COMPILE_REJECTED', 'code': code}
    return {'status': 'COMPILED', 'manifest_hash': hash_fn(substrate)(manifest),
            'compiled': compiled}


def ui_plan(profile_id, target_device, buttons, origin_model_run_id, evidence_refs,
            layout_version=1):
    widgets = []
    for b in buttons:
        if not b.get('manifest_hash'):
            raise WireError('BUTTON_NEEDS_MANIFEST_HASH')
        widgets.append({'widget_id': b['widget_id'], 'kind': 'button', 'label': b['label'],
                        'permission_label': b.get('permission_label', ''),
                        'binding': {'manifest_hash': b['manifest_hash'], 'inputs': dict(b.get('inputs', {}))}})
    plan = {'evidence_refs': list(evidence_refs), 'layout_version': layout_version,
            'origin_model_run_id': origin_model_run_id, 'profile_id': profile_id,
            'target_device': target_device, 'widgets': widgets}
    plan['plan_hash'] = 'sha256:' + S.digest(plan)
    return plan
