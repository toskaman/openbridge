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


def build_ui_prompt(intent_text, devices, primitive_ids):
    """Prompt offered to the Meta model at runtime (offline-built, deterministic)."""
    lines = ['UI_DRAFT v1. Intent: %s.' % (intent_text.strip()[:200]),
             'Widgets allowed: text|button|status. Reply with exactly one JSON patch:',
             '{"schema_version": %d, "patch_id": "<id>", "target_opaque_id": "<opaque device id>", '
             '"origin": "meta_generated", "model_run_id": "<run>", "widgets": '
             '[{"widget_id": "<id>", "kind": "text|button|status", "label": "<=80 chars>", '
             '"binding_primitive": "<one of the Primitives>", "params": {scalars only}}]}.' % S.SCHEMA_VERSION,
             'Primitives: %s.' % ','.join(sorted(primitive_ids)),
             'Devices:']
    for d in devices or []:
        lines.append('- %s (%s)' % (d.get('label', '?'), d.get('category', '?')))
    lines.append('Copy every id character-for-character. Refuse (no JSON) when the request '
                 'needs a widget kind, primitive or device not listed above.')
    return '\n'.join(lines)
