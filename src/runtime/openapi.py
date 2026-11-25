"""OpenAPI 3.0 description of the local /api/v2 surface.

Coverage is complete and enforced: tests/runtime/test_openapi.py fails when any GET_ROUTES or
POST_ROUTES entry is missing here, so the spec cannot rot as routes are added. Human summaries
are curated in SUMMARIES (mechanical fallback otherwise); request shapes are exact for the key
mutating routes in SCHEMAS and generic JSON objects elsewhere — shapes deepen over time.

Regenerate the committed file after touching routes or summaries:
    python -m src.runtime.openapi
writes docs/api/openapi.json (repo-relative). Third-party companions and the partner kit's
--from-openapi consumer start here.
"""
import json
from pathlib import Path

SPEC_REVISION = '1.0'

ERROR = {'type': 'object', 'properties': {'error': {'type': 'string'}}, 'required': ['error']}


def _err(*codes):
    out = {}
    for c in codes:
        out[str(c)] = {'description': {400: 'Bad request', 404: 'Unknown target',
                                       409: 'Conflict / consent required',
                                       503: 'Dependency unavailable'}[c],
                       'content': {'application/json': {'schema': ERROR}}}
    return out


SUMMARIES = {
    '/api/v2/ai/providers': ('AI providers', 'Configured command models and which one is active.'),
    '/api/v2/capabilities': ('Capabilities', 'Live device capabilities with STATUS vocabulary.'),
    '/api/v2/capabilities/explore': ('Explore capabilities', 'Probe what a device can do (read-only).'),
    '/api/v2/catalog': ('Device catalog', 'Known device classes and their integration status.'),
    '/api/v2/command/parse': ('Parse a command', 'Map free text to a skill proposal (no execution).'),
    '/api/v2/command/approve': ('Approve a command', 'Owner approves exactly one proposed command.'),
    '/api/v2/command/execute': ('Execute a command', 'Run an approved command through the gate.'),
    '/api/v2/companion/commands': ('Companion commands', 'Commands queued for paired Companions.'),
    '/api/v2/contract': ('Fabric contract', 'Contract version and schema.'),
    'POST /api/v2/dashboards/save': ('Save a dashboard', 'Persist a dashboard layout.'),
    '/api/v2/diagnosis': ('Diagnosis', 'What is wrong and what to do, in plain words.'),
    '/api/v2/events': ('Events', 'Recent timeline events.'),
    '/api/v2/execute': ('Execute a primitive', 'Run one typed primitive with receipts and Undo.'),
    '/api/v2/facts': ('Facts', 'Observed device facts.'),
    '/api/v2/graph': ('Device graph', 'Devices, links and capabilities snapshot.'),
    '/api/v2/hardware/facts': ('Hardware facts', 'This PC: CPU, RAM, GPU, radios.'),
    '/api/v2/library': ('Skill library', 'Saved skills: proposals, runs, buttons.'),
    'POST /api/v2/library/approve': ('Approve a skill', 'Approve exactly one saved recipe.'),
    'POST /api/v2/library/run': ('Run a skill', 'Run one approved recipe now.'),
    'POST /api/v2/library/enable': ('Enable/disable a skill', 'Toggle a recipe without deleting it.'),
    'POST /api/v2/library/remove': ('Remove a skill', 'Delete a recipe permanently.'),
    '/api/v2/primitives': ('Primitives', 'Typed action catalog with schemas and reversibility.'),
    '/api/v2/recovery': ('Recovery', 'Pending Undo and recovery state.'),
    '/api/v2/relays': ('Relays', 'Paired relay devices and routes.'),
    '/api/v2/remote_controls': ('Remote controls', 'Buttons granted to paired Companions.'),
    'POST /api/v2/remote_controls/skills': ('Grant skill buttons', 'Show approved skills as Companion buttons.'),
    '/api/v2/routes': ('Routes', 'How each device is reached.'),
    'POST /api/v2/route_intel/dispatch': ('Dispatch a route', 'Send a command down one route.'),
    '/api/v2/skill_routes': ('Skill routes', 'Which device serves each skill.'),
    '/api/v2/skills': ('Skills', 'Voice/command skill registry with policies.'),
    'POST /api/v2/skill_invoke': ('Invoke a skill', 'Run one registry skill through the gate.'),
    '/api/v2/timeline': ('Timeline', 'Receipts and events, newest first.'),
    'POST /api/v2/transplant/run': ('Run a transplant', 'Move a proven feature between devices.'),
    'POST /api/v2/workflows/run': ('Run a workflow', 'Start one multi-step workflow.'),
    '/api/v2/voice/intent': ('Voice intent', 'Map transcribed speech to an intent.'),
    '/api/v2/voice/transcribe': ('Transcribe', 'Speech to text on this PC.'),
    '/api/v2/watches': ('Watches', 'State watches feeding automations.'),
}

SCHEMAS = {
    'POST /api/v2/execute': {'required': [],
                             'properties': {'primitive_id': {'type': 'string'},
                                            'device_key': {'type': 'string'},
                                            'params': {'type': 'object'},
                                            'consent': {'type': 'boolean'},
                                            'idempotency_key': {'type': 'string', 'maxLength': 96}}},
    'POST /api/v2/library/approve': {'required': ['id', 'consent'],
                                     'properties': {'id': {'type': 'string'}, 'consent': {'type': 'boolean'}}},
    'POST /api/v2/library/run': {'required': ['id', 'consent'],
                                 'properties': {'id': {'type': 'string'}, 'consent': {'type': 'boolean'}}},
    'POST /api/v2/library/enable': {'required': ['id', 'enabled', 'consent'],
                                    'properties': {'id': {'type': 'string'}, 'enabled': {'type': 'boolean'},
                                                   'consent': {'type': 'boolean'}}},
    'POST /api/v2/library/remove': {'required': ['id', 'consent'],
                                    'properties': {'id': {'type': 'string'}, 'consent': {'type': 'boolean'}}},
    'POST /api/v2/remote_controls/skills': {'required': ['relay_id', 'recipe_ids', 'consent'],
                                            'properties': {'relay_id': {'type': 'string'},
                                                           'recipe_ids': {'type': 'array',
                                                                          'items': {'type': 'string'}},
                                                           'consent': {'type': 'boolean'}}},
}


def _auto_summary(path):
    words = [w for w in path.split('/api/v2/')[-1].replace('_', ' ').replace('-', ' ').split('/') if w]
    return ' '.join(words).title() or 'API'


def _operation_id(method, path):
    return method.lower() + '_' + path.split('/api/v2/')[-1].replace('/', '_').replace('-', '_')


def build():
    from src.runtime import api_v2
    paths = {}
    for path in sorted(set(api_v2.GET_ROUTES) | set(api_v2.POST_ROUTES)):
        item = {}
        for method in [m for m, routes in (('get', api_v2.GET_ROUTES), ('post', api_v2.POST_ROUTES)) if path in routes]:
            key = '%s %s' % (method.upper(), path)
            summary, desc = SUMMARIES.get(key, SUMMARIES.get(path, (None, None)))
            op = {'operationId': _operation_id(method, path),
                  'summary': summary or _auto_summary(path)}
            if desc:
                op['description'] = desc
            if method == 'post':
                schema = SCHEMAS.get(key)
                if schema is None:
                    props = {'type': 'object'}
                    req = None
                else:
                    props = {'type': 'object', 'properties': schema['properties'],
                             'additionalProperties': False}
                    req = schema['required'] or None
                    if req:
                        props['required'] = req
                op['requestBody'] = {'required': True,
                                     'content': {'application/json': {'schema': props}}}
            op['responses'] = dict({'200': {'description': 'OK'}}, **_err(400, 404, 409, 503))
            item[method] = op
        paths[path] = item
    return {'openapi': '3.0.3',
            'info': {'title': 'OpenBridge local API', 'version': SPEC_REVISION,
                     'description': 'The PC-local HTTP API a browser app or companion speaks to. '
                                    'All routes live under /api/v2; mutating routes take JSON and answer JSON.'},
            'servers': [{'url': 'http://127.0.0.1:18765', 'description': 'Default (python -m src.server --port).'}],
            'paths': paths}


def main():
    root = Path(__file__).resolve().parent.parent.parent
    out = root / 'docs' / 'api' / 'openapi.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=1) + '\n', encoding='utf-8')
    print('wrote %s (%d paths)' % (out.relative_to(root).as_posix(), len(build()['paths'])))


if __name__ == '__main__':
    main()
