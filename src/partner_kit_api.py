# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 the OpenBridge author. This file and the files it generates are licensed under the Apache License,
# Version 2.0 (LICENSES/Apache-2.0.txt), unlike the rest of OpenBridge (PolyForm Strict 1.0.0, see docs/LICENSING.md).
"""Bring your device, leave with an integration: an OpenAPI 3 description -> a device spec -> adapter, emulator, tests.

`api_spec(openapi)` reads the description and decides, with fixed rules a partner can predict:
- READ: the scalar fields of the JSON object returned by a GET (a path with "state" or "status" first);
- WRITABLE (reversible, read back, exact Undo): bounded scalar fields of a PUT/PATCH/POST body that READ also reports;
- COMMANDS (momentary, consent per command): POSTs with no body, and bounded body fields READ does not report;
- POLICY (always refused): anything whose name or path mentions firmware, update, reset, unlock, password, etc.;
  a field that looks like a secret (password, token, key) is not even read;
- skipped: everything else, with the reason, so nothing is silently dropped.
A field with no enum and no minimum/maximum is skipped: an allowlist needs bounds.

The same rules run in the browser (site/js/integrate-core.js); tests/unit/test_partner_kit_api.py checks that both
give the same files. Standard library only.
"""
import re

DANGEROUS = re.compile(r'firmware|ota|update|upgrade|flash|reset|factory|reboot|unlock|disarm|password|passcode|'
                       r'credential|token|secret|wifi|ssid|delete|erase|wipe|debug|shell|exec|pair', re.I)
SECRET = re.compile(r'password|passcode|credential|token|secret|api_?key|private', re.I)     # never even read
SCALARS = ('string', 'integer', 'number', 'boolean')
MAX_SPAN = 10000
METHODS = ('put', 'patch', 'post')


class SpecError(ValueError):
    pass


def snake(text):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(text or ''))
    s = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_').lower()
    return s[:40] or 'value'


def _ref(doc, node, depth=0):
    while isinstance(node, dict) and '$ref' in node:
        ref = node['$ref']
        if depth > 10 or not isinstance(ref, str) or not ref.startswith('#/'):
            raise SpecError('only local $ref are supported: %r' % ref)
        cur = doc
        for part in ref[2:].split('/'):
            cur = cur.get(part.replace('~1', '/').replace('~0', '~')) if isinstance(cur, dict) else None
        if cur is None:
            raise SpecError('unresolved $ref %r' % ref)
        node, depth = cur, depth + 1
    return node


def _json_schema(doc, content):
    content = _ref(doc, content) or {}
    for mime in ('application/json', 'application/json; charset=utf-8'):
        if isinstance(content.get(mime), dict):
            return _ref(doc, content[mime].get('schema') or {})
    return None


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _values(prop):
    """Allowed values of a scalar property: a list, {'min', 'max'} for an integer range, or None (unbounded)."""
    if isinstance(prop.get('enum'), list) and prop['enum'] and all(isinstance(v, (str, int, float, bool)) for v in prop['enum']):
        return [_num(v) for v in prop['enum']]
    t = prop.get('type')
    if t == 'boolean':
        return [True, False]
    if t in ('integer', 'number') and isinstance(prop.get('minimum'), (int, float)) and isinstance(prop.get('maximum'), (int, float)):
        lo, hi = int(prop['minimum']), int(prop['maximum'])
        if lo <= hi and hi - lo <= MAX_SPAN:
            return {'min': lo, 'max': hi}
    return None


def _default(prop, values):
    for k in ('default', 'example'):
        if k in prop and isinstance(prop[k], (str, int, float, bool)):
            return _num(prop[k])
    if isinstance(values, list):
        return values[-1] if prop.get('type') == 'boolean' else values[0]
    if isinstance(values, dict):
        return values['min']
    return {'string': '', 'integer': 0, 'number': 0, 'boolean': False}.get(prop.get('type'), '')


def _unit(name, prop):
    unit = prop.get('x-unit')
    if isinstance(unit, str):
        return unit[:8]
    return '%' if 'percent' in name or name.endswith('_pct') else ''


def _props(doc, schema):
    schema = _ref(doc, schema or {})
    if not isinstance(schema, dict) or schema.get('type', 'object') != 'object' or not isinstance(schema.get('properties'), dict):
        return None
    return [(snake(k), k, _ref(doc, v) if isinstance(v, dict) else {}) for k, v in sorted(schema['properties'].items())]


def api_spec(doc):
    if not isinstance(doc, dict) or not str(doc.get('openapi', '')).startswith('3'):
        raise SpecError('an OpenAPI 3 description (JSON) is needed; convert Swagger 2 or YAML first')
    paths = doc.get('paths')
    if not isinstance(paths, dict) or not paths:
        raise SpecError('the description has no paths')
    servers = doc.get('servers') if isinstance(doc.get('servers'), list) else []
    base = servers[0].get('url', '') if servers and isinstance(servers[0], dict) else ''
    title = str((doc.get('info') or {}).get('title') or 'Device')[:60]
    skipped = []

    # READ: a GET returning a JSON object; "state"/"status" paths first, then alphabetical.
    gets = []
    for path in sorted(paths):
        op = _ref(doc, paths[path]).get('get') if isinstance(paths[path], dict) else None
        if not isinstance(op, dict):
            continue
        resp = _ref(doc, (op.get('responses') or {}).get('200') or {})
        props = _props(doc, _json_schema(doc, resp.get('content') or {}) or {}) if isinstance(resp, dict) else None
        if '{' in path:
            skipped.append('GET %s: path parameters are not filled automatically' % path)
        elif props:
            gets.append((0 if re.search(r'state|status', path, re.I) else 1, path, props))
    if not gets:
        raise SpecError('no GET returns a JSON object to read the device state from')
    gets.sort(key=lambda g: (g[0], g[1]))
    _, read_path, read_props = gets[0]
    for _, p, _ in gets[1:]:
        skipped.append('GET %s: only one state endpoint is read (%s)' % (p, read_path))
    fields, policy, field_props = {}, {}, {}
    for name, raw, prop in read_props:
        if SECRET.search(name):
            skipped.append('field %s: looks like a secret, never read' % raw)
            policy[name] = '%s is never read or changed by OpenBridge (found in the API description).' % raw
            continue
        if prop.get('type') not in SCALARS:
            skipped.append('field %s: not a plain value (object or list)' % raw)
            continue
        fields[name] = {'key': raw, 'unit': _unit(name, prop), 'default': _default(prop, _values(prop))}
        field_props[name] = raw

    writable, commands = {}, {}
    for path in sorted(paths):
        item = _ref(doc, paths[path]) if isinstance(paths[path], dict) else {}
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            where = '%s %s' % (method.upper(), path)
            if '{' in path:
                skipped.append('%s: path parameters are not filled automatically' % where)
                continue
            if DANGEROUS.search(path):
                policy[snake(path.rstrip('/').rsplit('/', 1)[-1])] = '%s is never used by OpenBridge (found in the API description).' % where
                continue
            body = _ref(doc, op.get('requestBody') or {})
            props = _props(doc, _json_schema(doc, body.get('content') or {}) or {}) if isinstance(body, dict) and body else None
            if not props:
                if body:
                    skipped.append('%s: body is not a JSON object with properties' % where)
                    continue
                if method != 'post':
                    skipped.append('%s: no body' % where)
                    continue
                name = snake(path.rstrip('/').rsplit('/', 1)[-1])
                if name in commands or name in writable:
                    skipped.append('%s: name %s already used' % (where, name))
                    continue
                commands[name] = {'values': None, 'method': 'POST', 'path': path, 'body': None}
                continue
            for name, raw, prop in props:
                if DANGEROUS.search(name):
                    policy[name] = '%s is never changed by OpenBridge (found in the API description).' % raw
                    continue
                if prop.get('type') not in SCALARS:
                    skipped.append('%s field %s: not a plain value' % (where, raw))
                    continue
                values = _values(prop)
                if values is None:
                    skipped.append('%s field %s: no enum or minimum/maximum, so no allowlist' % (where, raw))
                    continue
                if name in writable or name in commands:
                    skipped.append('%s field %s: already mapped' % (where, raw))
                    continue
                if name in fields:
                    writable[name] = {'values': values, 'method': method.upper(), 'path': path, 'body': raw}
                else:
                    commands[name] = {'values': values, 'method': method.upper(), 'path': path, 'body': raw}
    for name in list(fields):
        if DANGEROUS.search(name) and name not in policy:
            policy[name] = '%s is never changed by OpenBridge (found in the API description).' % field_props[name]
    if not writable and not commands:
        skipped.append('no bounded setting or command found: the adapter will only read')
    srt = lambda d: {k: d[k] for k in sorted(d)}
    return {'title': title, 'base_url': base, 'read': {'method': 'GET', 'path': read_path, 'fields': srt(fields)},
            'writable': srt(writable), 'commands': srt(commands), 'policy': srt(policy), 'skipped': skipped}


# ---------- Python literals (the browser has the same function, so both write the same files) ----------

def pylit(v):
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if v is None:
        return 'None'
    if isinstance(v, (int, float)):
        v = _num(v)
        return str(v) if isinstance(v, int) else repr(v)
    if isinstance(v, str):
        return "'" + v.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r') + "'"
    if isinstance(v, dict) and set(v) == {'min', 'max'}:
        return 'range(%d, %d)' % (v['min'], v['max'] + 1)
    if isinstance(v, (list, tuple)):
        items = [pylit(x) for x in v]
        return '(' + items[0] + ',)' if len(items) == 1 else '(' + ', '.join(items) + ')'
    if isinstance(v, dict):
        return '{' + ', '.join('%s: %s' % (pylit(k), pylit(x)) for k, x in v.items()) + '}'
    raise SpecError('cannot write %r' % (v,))


def block(name, mapping, indent=4):
    """A module-level dict, one entry per line (readable diffs)."""
    if not mapping:
        return '%s = {}' % name
    pad = ' ' * indent
    return '%s = {\n%s\n}' % (name, '\n'.join('%s%s: %s,' % (pad, pylit(k), pylit(v)) for k, v in mapping.items()))


def template_values(spec):
    fields = spec['read']['fields']
    return {
        'read_block': block('READ', {k: f['unit'] for k, f in fields.items()}),
        'writable_block': block('WRITABLE', {k: w['values'] for k, w in spec['writable'].items()}),
        'commands_block': block('COMMANDS', {k: c['values'] for k, c in spec['commands'].items()}),
        'policy_block': 'POLICY = {}' if not spec['policy'] else 'POLICY = {\n%s\n}' % '\n'.join(
            "    (%s, '*'): %s," % (pylit(k), pylit(r)) for k, r in spec['policy'].items()),
        'base_url': pylit(spec['base_url']),
        'read_path': pylit(spec['read']['path']),
        'read_keys': block('READ_KEYS', {k: f['key'] for k, f in fields.items()}),
        'write_routes': block('WRITE_ROUTES', {k: [w['method'], w['path'], w['body']] for k, w in spec['writable'].items()}),
        'command_routes': block('COMMAND_ROUTES', {k: [c['method'], c['path'], c['body']] for k, c in spec['commands'].items()}),
        'state_block': block('STATE', {k: f['default'] for k, f in fields.items()}, indent=4),
        'endpoints_md': '\n'.join(
            ['| Read | `GET %s` | %s |' % (spec['read']['path'], ', '.join('`%s`' % k for k in fields) or '-')] +
            ['| Setting `%s` | `%s %s` | read back, exact Undo |' % (k, w['method'], w['path']) for k, w in spec['writable'].items()] +
            ['| Command `%s` | `%s %s` | momentary, consent per command |' % (k, c['method'], c['path']) for k, c in spec['commands'].items()] +
            ['| Refused `%s` | | %s |' % (k, r) for k, r in spec['policy'].items()]),
        'skipped_md': '\n'.join('- %s' % s for s in spec['skipped']) or '- nothing',
    }
