"""Manual2Skill compiler slice: structured manual fragment -> guarded, versioned skill.

Every parameter, warning and command must cite its source span (e.g. 'manual.pdf:12');
uncited claims are rejected at compile time. Warnings that parse as range constraints
('never exceed 10 V ...') become executable guards; all other warnings are carried as
mandatory operator_read text, never silently dropped. replay() verifies rendered commands
against a recorded trace fixture before any skill ships.
"""
import hashlib
import json
import re

MAX_NAME = 64
_RANGE_WARNING = re.compile(r"(?:never exceed|do not exceed|does not exceed|maximum of|max(?:imum)?)\s+(\d+(?:\.\d+)?)\s*([A-Za-z/%]+)", re.IGNORECASE)


class ManualSkillError(RuntimeError):
    pass


def _require_cite(item, kind):
    cite = item.get('cite')
    if not isinstance(cite, str) or not cite or len(cite) > 128:
        raise ManualSkillError(f'{kind} without a source citation is rejected')
    return cite


def _is_name(value):
    return isinstance(value, str) and bool(value) and len(value) <= MAX_NAME and value.replace('_', '').isalnum()


def compile_skill(fragment):
    if not isinstance(fragment, dict):
        raise ManualSkillError('Fragment must be an object')
    name, version = fragment.get('name'), fragment.get('version')
    if not _is_name(name):
        raise ManualSkillError('Skill name must be alphanumeric/underscore up to 64 chars')
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ManualSkillError('Skill version must be semver x.y.z')
    params, warnings, commands = fragment.get('parameters') or [], fragment.get('warnings') or [], fragment.get('commands') or []
    if not isinstance(params, list) or not isinstance(warnings, list) or not isinstance(commands, list) or not commands:
        raise ManualSkillError('parameters/warnings must be lists; at least one command template is required')
    try:
        blob = json.dumps(fragment, sort_keys=True).encode()
    except (TypeError, ValueError) as error:
        raise ManualSkillError(f'Fragment is not JSON-shaped: {error}') from None
    provenance, guards, operator_read, templates, by_unit = [], [], [], [], {}
    for p in params:
        if not isinstance(p, dict):
            raise ManualSkillError('parameter must be an object')
        for field in ('name', 'unit', 'min', 'max'):
            if field not in p:
                raise ManualSkillError(f'parameter misses {field!r}')
        cite = _require_cite(p, 'parameter')
        if not _is_name(p['name']):
            raise ManualSkillError(f'Bad parameter name ({cite})')
        if not isinstance(p['unit'], str) or not p['unit'] or len(p['unit']) > 16:
            raise ManualSkillError(f'Bad unit ({cite})')
        if type(p['min']) not in (int, float) or type(p['max']) not in (int, float) or not p['min'] <= p['max']:
            raise ManualSkillError(f"parameter {p['name']} has an invalid [min, max] range ({cite})")
        provenance.append(cite)
        guards.append({'param': p['name'], 'min': p['min'], 'max': p['max'], 'cite': cite})
        by_unit.setdefault(p['unit'].lower(), []).append(p['name'])
    for w in warnings:
        if not isinstance(w, dict):
            raise ManualSkillError('warning must be an object')
        cite = _require_cite(w, 'warning')
        text = w.get('text')
        if not isinstance(text, str) or not text or len(text) > 2000:
            raise ManualSkillError(f'warning text required ({cite})')
        provenance.append(cite)
        matched = re.search(_RANGE_WARNING, text)
        if matched and matched.group(2).lower() in by_unit:
            for pname in by_unit[matched.group(2).lower()]:
                guards.append({'param': pname, 'min': None, 'max': float(matched.group(1)), 'cite': cite})
        else:
            operator_read.append(text)
    for c in commands:
        if not isinstance(c, dict):
            raise ManualSkillError('command must be an object')
        cite = _require_cite(c, 'command')
        template = c.get('template')
        if not isinstance(template, str) or not template or len(template) > 2000:
            raise ManualSkillError(f'command template required ({cite})')
        provenance.append(cite)
        templates.append({'template': template, 'cite': cite})
    return {'name': name, 'version': version, 'title': fragment.get('title', ''), 'guards': guards,
            'operator_read': operator_read, 'commands': templates, 'provenance': sorted(set(provenance)),
            'fragment_hash': hashlib.sha256(blob).hexdigest()}


def render_command(skill, params):
    if not isinstance(params, dict):
        raise ManualSkillError('params must be an object')
    known = {g['param'] for g in skill['guards']}
    if set(params) - known:
        raise ManualSkillError(f'Unknown params {sorted(set(params) - known)}; guarded params: {sorted(known)}')
    values, violations = {}, []
    for g in skill['guards']:
        if g['param'] not in params:
            continue
        v = params[g['param']]
        if type(v) not in (int, float):
            raise ManualSkillError(f"{g['param']} must be a number ({g['cite']})")
        if (g['min'] is not None and v < g['min']) or (g['max'] is not None and v > g['max']):
            violations.append(f"{g['param']}={v} outside [{g['min']}, {g['max']}] ({g['cite']})")
        values[g['param']] = v
    if violations:
        raise ManualSkillError('; '.join(violations))
    try:
        return skill['commands'][0]['template'].format(**values)
    except KeyError as error:
        raise ManualSkillError(f'template needs {error} (provide it in params)') from None


def replay(skill, trace):
    if not isinstance(trace, list) or not trace:
        raise ManualSkillError('trace must be a non-empty list')
    passed, mismatches = 0, []
    for i, step in enumerate(trace):
        if not isinstance(step, dict):
            raise ManualSkillError(f'trace step {i} is malformed')
        rendered = render_command(skill, step.get('params') or {})
        if rendered == step.get('expected'):
            passed += 1
        else:
            mismatches.append({'step': i, 'rendered': rendered, 'expected': step.get('expected')})
    return {'passed': passed, 'failed': len(mismatches), 'mismatches': mismatches}
