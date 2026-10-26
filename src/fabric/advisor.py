"""Coverage advisor: deterministic candidate steps from the graph; a local Meta model may pick and explain one.
The model sees categories, counts and step ids only (no labels, addresses or identifiers) and cannot invent a step."""
import json
import re
from decimal import Decimal
from src.ai.broker import ModelBlocked

GOALS = ('extend_coverage', 'find_bluetooth', 'tidy_inventory')
LIMIT = 'Discovery does not prove ownership or control; every step still needs owner action and policy checks.'


def candidate_steps(snapshot):
    steps = []
    refs = {d['key']: f'd{i + 1}' for i, d in enumerate(snapshot['devices'])}
    for d in snapshot['devices']:
        caps = {c['name']: c['status'] for c in d['capabilities']}
        r = refs[d['key']]
        if caps.get('lan_inventory') == 'BLOCKED':
            steps.append({'id': f'authorize_freebox:{r}', 'kind': 'authorize_freebox', 'category': d['category'], 'unlocks': 'lan_inventory'})
        if caps.get('ble_relay') == 'NOT_SUPPORTED':
            steps.append({'id': f'install_companion:{r}', 'kind': 'install_companion', 'category': d['category'], 'unlocks': 'ble_scan'})
        if caps.get('tv_remote_protocol') and 'inspect' not in caps:
            steps.append({'id': f'pair_wifi_adb:{r}', 'kind': 'pair_wifi_adb', 'category': d['category'], 'unlocks': 'inspect'})
        if d.get('possibly_same_as') and d['key'] < min(d['possibly_same_as']):
            steps.append({'id': f'review_duplicate:{r}', 'kind': 'review_duplicate', 'category': d['category'], 'unlocks': 'identity'})
    return steps[:20], refs


PRIORITY = {'extend_coverage': ('authorize_freebox', 'pair_wifi_adb', 'install_companion', 'review_duplicate'),
            'find_bluetooth': ('install_companion', 'pair_wifi_adb', 'authorize_freebox', 'review_duplicate'),
            'tidy_inventory': ('review_duplicate', 'authorize_freebox', 'pair_wifi_adb', 'install_companion')}


def rule_choice(steps, goal):
    """Deterministic baseline: fixed priority per goal, prefers mains-powered TVs for relays."""
    order = PRIORITY[goal]
    ranked = sorted(steps, key=lambda s: (order.index(s['kind']), 0 if s['category'] == 'tv' else 1, s['id']))
    return ranked[0]['id'] if ranked else None


def summary_counts(snapshot):
    counts = {}
    for d in snapshot['devices']:
        counts[d['category']] = counts.get(d['category'], 0) + 1
    return {'devices': len(snapshot['devices']), 'links': len(snapshot['links']), 'by_category': counts,
            'indirect_devices': sum(1 for l in snapshot['links'] if l['parent'] != 'pc')}


def advise(broker, snapshot, goal):
    if goal not in GOALS:
        raise ModelBlocked('Unknown goal')
    steps, _ = candidate_steps(snapshot)
    if not steps:
        return {'step': None, 'source': 'rules', 'summary': 'No further discovery step is available.', 'candidates': []}
    counts = summary_counts(snapshot)
    ids = [s['id'] for s in steps]
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['summary', 'step', 'uncertainty'],
              'properties': {'summary': {'type': 'string'}, 'step': {'type': 'string', 'enum': ids},
                             'uncertainty': {'type': 'string', 'enum': [LIMIT]}}}
    payload = {'model': broker.model_id, 'stream': False, 'format': schema, 'keep_alive': '60s', **broker.extra,
               'options': {**broker.options, 'num_predict': 400},
               'messages': [{'role': 'system', 'content':
                   'You advise the owner of a home device graph. Respond in English as compact JSON matching the schema. '
                   'Choose exactly one step id from the candidates that best serves the owner goal and explain why in one or two sentences, '
                   'using only the supplied counts and categories. Do not invent devices, numbers or capabilities. '
                   'install_companion turns a phone or TV into a Bluetooth relay; mains-powered TVs are better relays than phones. '
                   'authorize_freebox reveals devices the router knows; pair_wifi_adb makes a TV inspectable; review_duplicate clarifies identity. '
                   'The uncertainty field must use the exact policy text.'},
                   {'role': 'user', 'content': json.dumps({'goal': goal, 'graph': counts, 'candidates': steps}, sort_keys=True)}]}
    proposal, response = broker._call(payload)
    if not isinstance(proposal, dict) or set(proposal) != {'summary', 'step', 'uncertainty'} or proposal['step'] not in ids:
        raise ModelBlocked('Advisor output invalid')
    if proposal['uncertainty'] != LIMIT or not 1 <= len(proposal['summary']) <= 600:
        raise ModelBlocked('Advisor must keep the policy limitation')
    text = proposal['summary'].strip()
    if len(text) < 25 or text.startswith(('{', '[')) or text in ids or len(re.findall(r'[A-Za-z]{3,}', text)) < 5:
        raise ModelBlocked('Advisor explanation is not a usable sentence')
    allowed = {Decimal(str(v)) for v in (counts['devices'], counts['links'], counts['indirect_devices'], *counts['by_category'].values())}
    allowed |= {Decimal(n) for s in ids for n in re.findall(r'\d+', s)}
    for n in re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w])', proposal['summary']):
        if Decimal(n) not in allowed:
            raise ModelBlocked('Advisor introduced an unverified number')
    return {'step': proposal['step'], 'source': broker.model_id, 'summary': proposal['summary'], 'candidates': ids,
            'rule_choice': rule_choice(steps, goal), 'usage': {'prompt_tokens': response['prompt_eval_count'], 'completion_tokens': response['eval_count']}}
