"""S2 UI drafting (Forge side, offline): slot grammar + model prompt builder.

Honest split: at runtime a Meta model drafts the patch from build_ui_prompt()
and v4_ui.validate_patch enforces the schema. Offline we prove the mechanics:
slot-built candidates validate, and every unsupported request is refused with
an exact code BEFORE reaching a renderer. Rendering/publish stays Claude-side.
"""
import hashlib

from src.forge import v4_schemas as S
from src.forge import v4_ui

ACTIONS = {'add_button', 'add_status', 'add_text'}


class DraftError(ValueError):
    pass


def _widget_id(label, primitive):
    return 'w-' + hashlib.sha256(('%s\x00%s' % (label, primitive)).encode()).hexdigest()[:12]


def draft_from_slots(slots, primitive_ids, model_run_id):
    """Build a patch candidate from explicit slots. Refuses, never invents."""
    if not isinstance(slots, dict):
        raise DraftError('SLOTS_MUST_BE_OBJECT')
    action = slots.get('action')
    if action not in ACTIONS:
        raise DraftError('UNSUPPORTED_ACTION: %r' % (action,))
    kind = {'add_button': 'button', 'add_status': 'status', 'add_text': 'text'}[action]
    primitive = slots.get('primitive')
    if primitive not in (primitive_ids or ()):
        raise DraftError('UNKNOWN_BINDING: %r' % (primitive,))
    params = slots.get('params', {})
    if not isinstance(params, dict) or any(not isinstance(v, (str, int, float, bool)) for v in params.values()):
        raise DraftError('PARAMS_MUST_BE_SCALARS')
    label = slots.get('label')
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
        raise DraftError('LABEL_INVALID')
    target = slots.get('target_opaque_id')
    if not isinstance(target, str) or not target.startswith('opaque:'):
        raise DraftError('TARGET_MUST_BE_OPAQUE_REF')
    patch = {'schema_version': S.SCHEMA_VERSION,
             'patch_id': 'p-' + hashlib.sha256(('%s\x00%s\x00%s' % (action, label, primitive)).encode()).hexdigest()[:12],
             'target_opaque_id': target, 'origin': 'meta_generated',
             'model_run_id': model_run_id,
             'widgets': [{'widget_id': _widget_id(label, primitive), 'kind': kind,
                          'label': label.strip(), 'binding_primitive': primitive,
                          'params': dict(params)}]}
    return v4_ui.validate_patch(patch, primitive_ids)


def emit_install_plan(patch, manifests, target_device_fp, profile_id,
                      layout_version, evidence_refs=(), sources=None):
    """Map an S2 patch to Claude's UIViewPlan (contract C1, offline).

    manifests: {binding_primitive: manifest_hash} of COMPILED+APPROVED
    manifests — refused when missing, never invented. sources: {status
    widget_id: actionable widget_id}. Returns (plan, needed_hashes); the
    caller assembles install bindings after owner approval. plan_hash is
    computed with the kernel's own function.
    """
    import re
    from src.substrate import kernel as K
    if not isinstance(patch, dict) or not isinstance(patch.get('widgets'), list) \
            or not patch['widgets']:
        raise DraftError('PATCH_SHAPE')
    if not isinstance(target_device_fp, str) or not target_device_fp:
        raise DraftError('TARGET_FP_REQUIRED')
    if not isinstance(profile_id, str) or not profile_id:
        raise DraftError('PROFILE_REQUIRED')
    if not isinstance(layout_version, int) or isinstance(layout_version, bool) \
            or layout_version < 1:
        raise DraftError('LAYOUT_VERSION_INVALID')
    widgets = []
    needed = set()
    kinds = {w.get('widget_id') for w in patch['widgets']}
    for w in patch['widgets']:
        label = w.get('label', '')
        if not isinstance(label, str) or K.BAD_TEXT.search(label):
            raise DraftError('INJECTION_SUSPECT: %r' % (w.get('widget_id'),))
        kind = w.get('kind')
        if kind == 'button':
            mh = (manifests or {}).get(w.get('binding_primitive'))
            if not isinstance(mh, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', mh):
                raise DraftError('UI_MANIFEST_REQUIRED: %s' % (w.get('widget_id'),))
            needed.add(mh)
            perm = 'Run %s' % (w.get('binding_primitive'),)
            if len(perm) > 60:
                raise DraftError('PERMISSION_LABEL_TOO_LONG')
            widgets.append({'widget_id': w['widget_id'], 'kind': 'button',
                            'label': label, 'binding': {'manifest_hash': mh, 'inputs': dict(w.get('params') or {})},
                            'permission_label': perm})
        elif kind == 'text':
            widgets.append({'widget_id': w['widget_id'], 'kind': 'label',
                            'label': label, 'binding': None, 'permission_label': ''})
        elif kind == 'status':
            src = (sources or {}).get(w['widget_id'])
            if src not in kinds:
                raise DraftError('STATUS_SOURCE_REQUIRED: %s' % (w.get('widget_id'),))
            widgets.append({'widget_id': w['widget_id'], 'kind': 'status',
                            'label': label, 'binding': None, 'permission_label': '',
                            'source': src})
        else:
            raise DraftError('WIDGET_KIND: %r' % (kind,))
    plan = {'target_device': target_device_fp, 'profile_id': profile_id,
            'layout_version': layout_version, 'widgets': widgets,
            'origin_model_run_id': patch.get('model_run_id'), 'evidence_refs': list(evidence_refs or [])}
    plan['plan_hash'] = K.manifest_hash(plan)
    return plan, needed


def build_ui_prompt(intent_text, devices, primitive_ids, hints=None):
    """Prompt offered to the Meta model at runtime (offline-built, deterministic)."""
    lines = ['UI_DRAFT v2. Intent: %s.' % (intent_text.strip()[:200]),
             'Reply with exactly one JSON response: {"outcome": "<proposal|refusal|needs_clarification|unsupported>", '
             '"patch": {<patch, ONLY when outcome is proposal>}, '
             '"reason": "<<=500 chars, for refusal/unsupported>", '
             '"clarifying_question": "<for needs_clarification>"}.',
             'A patch has exactly: {"schema_version": %d, "patch_id": "<id>", "target_opaque_id": "<opaque device id>", '
             '"origin": "meta_generated", "model_run_id": "<run>", "widgets": '
             '[{"widget_id": "<id>", "kind": "button", "label": "<=80 chars>", '
             '"binding_primitive": "<one of the Primitives>", "params": {match its hint}}]}.' % S.SCHEMA_VERSION,
             'Widgets allowed: text|button|status.',
             'Primitives (binding_primitive must be one of these; params must match its hint exactly, no extra keys):']
    for pid in sorted(primitive_ids or ()):
        hint = (hints or {}).get(pid, '')
        lines.append('- %s %s' % (pid, hint))
    lines.append('Devices:')
    for d in devices or []:
        line = '- %s (%s)' % (d.get('label', '?'), d.get('category', '?'))
        if d.get('opaque_id'):
            line += ' id %s' % (d['opaque_id'],)
        lines.append(line)
    lines.append('Copy every id character-for-character, including the opaque: prefix. '
                 'Compose 2 to 4 buttons covering the request. '
                 'Example (shape only, not the answer): {"schema_version": 1, "patch_id": "p-ex", '
                 '"target_opaque_id": "opaque:<copy-from-Devices-list>", '
                 '"origin": "meta_generated", "model_run_id": "mr-ex", "widgets": '
                 '[{"widget_id": "w-1", "kind": "button", "label": "Volume down", '
                 '"binding_primitive": "tv_volume_step", "params": {"direction": "down"}}]}. '
                 'When the request needs a widget kind, primitive or device not listed '
                 'above, reply {"outcome": "refusal", "reason": "<why, <=500 chars>"} '
                 'with NO patch. Never substitute an unrelated primitive to look '
                 'helpful: a wrong binding is worse than a refusal. Ask with '
                 '\'{"outcome": "needs_clarification", "clarifying_question": "<one "\''
                 'question>} ONLY when two listed primitives match equally well. '
                 '(No JSON at all is also read as a refusal.)')
    return '\n'.join(lines)
