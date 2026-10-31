"""V4 DynamicUIPlanner: schema-bound patches only. No scripts, no JS, no HTML."""
from src.forge import v4_schemas as S

WIDGET_KINDS = {'text', 'button', 'status'}
WIDGET_KEYS = {'widget_id', 'kind', 'label', 'binding_primitive', 'params'}
PATCH_KEYS = {'schema_version', 'patch_id', 'target_opaque_id', 'origin', 'model_run_id', 'widgets'}

# Ollama structured-output constraint (shape only; validate_patch re-checks
# every value deterministically).
UI_PATCH_JSON_SCHEMA = {'type': 'object',
    'required': ['schema_version', 'patch_id', 'target_opaque_id', 'origin',
                 'model_run_id', 'widgets'],
    'properties': {'schema_version': {'type': 'integer'}, 'patch_id': {'type': 'string'},
                   'target_opaque_id': {'type': 'string'}, 'origin': {'type': 'string'},
                   'model_run_id': {'type': 'string'},
                   'widgets': {'type': 'array', 'minItems': 1,
                       'items': {'type': 'object',
                           'required': ['widget_id', 'kind', 'label', 'binding_primitive', 'params'],
                           'properties': {'widget_id': {'type': 'string'}, 'kind': {'type': 'string'},
                                          'label': {'type': 'string'},
                                          'binding_primitive': {'type': 'string'},
                                          'params': {'type': 'object'}}}}}}


class UIError(ValueError):
    pass


def validate_patch(value, primitive_ids):
    if not isinstance(value, dict) or set(value) != PATCH_KEYS:
        raise UIError('PATCH_SHAPE')
    if value['schema_version'] != S.SCHEMA_VERSION or value['origin'] != 'meta_generated':
        raise UIError('PATCH_META')
    if not isinstance(value['widgets'], list) or not value['widgets']:
        raise UIError('WIDGETS_REQUIRED')
    for w in value['widgets']:
        if set(w) != WIDGET_KEYS:
            raise UIError('WIDGET_SHAPE: unexpected keys')
        if w['kind'] not in WIDGET_KINDS:
            raise UIError('WIDGET_KIND')
        if w['binding_primitive'] not in primitive_ids:
            raise UIError('UNKNOWN_BINDING')
        if not isinstance(w['params'], dict) or any(not isinstance(v, (str, int, float, bool)) for v in w['params'].values()):
            raise UIError('PARAMS_MUST_BE_SCALARS')
    return value
