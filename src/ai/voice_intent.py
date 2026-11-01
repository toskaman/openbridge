"""Voice/text -> typed intent (V4-10 + Campaign Two §4.6). Deterministic, French + English, no model required.

The transcript is untrusted text. It can only select one of a few typed intents that map to existing primitives;
it never carries a command string, a package name or an address. The result is a *proposal*: the owner reviews the
transcript and the proposal on screen, and execution still goes through the Executor (schema, consent, identity).
Voice is never an authorization factor (no voice biometrics).

Campaign Two §4.6 layers deterministic normalization and fail-closed screens
(src/ai/voice_normalize.py) in front of the legacy patterns:

- single-reading STT repairs (tellee->tele, blue tooth->bluetooth) feed
  matching only; a proposal may never rest on a repaired token (two-pass
  rule: clean match -> proposal path, repaired-only match -> clarification);
- uncertain verbs (mas/mais/mes in verb position, per Watch7 evidence),
  conflicting intents, bare fragments ('scan', 'check'), control presses,
  control-surface moves, volume changes and locate-my-device requests all
  yield clarification, never a proposal;
- the refusal list is extended (reboot, wipe/format, flash, unlock,
  purchases, physical access) with localized texts.

Legacy outcomes keep their byte-identical strings; every result gains the
machine-readable keys 'outcome' (proposal|needs_clarification|refusal|
unsupported), 'lang', 'clarifying_question' and 'normalization'.
"""
import re

from src.ai import voice_normalize as VN

INTENTS = {
    'discover': {'primitive_id': 'bounded_discovery', 'consent': False, 'says': 'Run one bounded discovery of this network'},
    'ble_scan_via_tv': {'primitive_id': 'relay_ble_scan', 'consent': True, 'says': 'Ask the TV Companion relay for one short Bluetooth scan'},
    'ble_scan_via_phone': {'primitive_id': 'relay_ble_scan', 'consent': True, 'says': 'Ask the phone Companion relay for one short Bluetooth scan'},
    'diagnose': {'primitive_id': 'diagnostic_report', 'consent': False, 'says': 'Read every readable device once and build a report'},
    'why_disconnect': {'primitive_id': 'diagnostic_probe', 'consent': False, 'says': 'Re-measure the device and show competing hypotheses'},
    'finish_session': {'primitive_id': 'session_cleanup', 'consent': True, 'says': 'Open the end-of-session restore list (you pick what to restore)'},
}
_P = [
    ('ble_scan_via_tv', r'\b(bluetooth|ble)\b.*\b(tv|tele|television|televiseur)\b|\b(tv|tele|television)\b.*\b(bluetooth|ble)\b'),
    ('ble_scan_via_phone', r'\b(bluetooth|ble)\b.*\b(phone|telephone|portable|mobile)\b|\b(phone|telephone)\b.*\b(bluetooth|ble)\b'),
    ('why_disconnect', r'\b(why|pourquoi)\b.*\b(disconnect\w*|deconnect\w*|drop\w*|coupe\w*|perd\w*|lost)\b'),
    ('finish_session', r'\b(finish|end|terminer|termine|fin)\b.*\bsession\b|\brestore\b|\brestaure\w*\b'),
    ('diagnose', r'\b(diagnos\w*|report|rapport|check|verifie\w*|health|sante)\b'),
    ('discover', r'\b(discover\w*|find|scan|decouvr\w*|trouve\w*|cherche\w*|devices|appareils)\b'),
]
REFUSE = r'\b(shut ?down|eteins|eteindre|power off|install\w*|uninstall\w*|desinstall\w*|factory|reset|reinitialis\w*|root|delete|supprime\w*|password|mot de passe)\b'


def _norm(t):
    return VN.fold(t)


def _meta(norm):
    return {'repairs': list(norm['repairs']),
            'uncertain_verb': norm['uncertain_verb'], 'lang_raw': norm['lang_raw']}


def _clarify(transcript, norm, text):
    return {'intent': None, 'outcome': 'needs_clarification', 'reason': text,
            'clarifying_question': text, 'transcript': transcript,
            'lang': norm['lang'], 'normalization': _meta(norm)}


def compile_intent(transcript, devices=(), lang_hint=None):
    """devices: [{'key','category'}] from the graph. -> proposal dict (never executed here).

    lang_hint ('fr'|'en'|None) is the short-command language guard: transcripts
    with zero signal words (e.g. 'scan bluetooth') detect as unknown, and
    without a hint that defaults to English — mislanguaging short commands
    from French speakers. Callers with locale info must pass it through.
    """
    if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 400:
        return {'intent': None, 'outcome': 'unsupported',
                'reason': 'empty or too long transcript'}
    norm = VN.normalize(transcript, lang_hint)
    t, fx, lang = norm['folded'], norm['fixed'], norm['lang']
    if re.search(REFUSE, fx):
        return {'intent': None, 'outcome': 'refusal',
                'reason': 'This request needs a manual, explicitly confirmed action; voice cannot start it.',
                'clarifying_question': None, 'transcript': transcript,
                'lang': lang, 'normalization': _meta(norm)}
    if VN.screen_refusal_extra(fx):
        text = VN.question('refusal_extra', lang)
        return {'intent': None, 'outcome': 'refusal', 'reason': text,
                'clarifying_question': None, 'transcript': transcript,
                'lang': lang, 'normalization': _meta(norm)}
    if VN.screen_control_press(fx):
        return _clarify(transcript, norm, VN.question('press', lang))
    if VN.screen_migration_shape(fx):
        return _clarify(transcript, norm, VN.question('migration', lang))
    if VN.screen_locate_shape(fx):
        return _clarify(transcript, norm, VN.question('locate', lang))
    if VN.screen_volume_shape(fx):
        return _clarify(transcript, norm, VN.question('volume', lang))
    conflict = VN.screen_conflict(fx)
    if conflict:
        if conflict['kind'] == 'finish':
            text = VN.conflict_finish_question(conflict['other'], lang)
        elif conflict['kind'] == 'targets':
            text = VN.question('conflict_targets', lang)
        else:
            text = VN.question('conflict_startstop', lang)
        return _clarify(transcript, norm, text)
    hits = [name for name, rx in _P if re.search(rx, t)]
    if hits and norm['uncertain_verb']:
        return _clarify(transcript, norm, VN.question('uncertain', lang))
    if hits and VN.is_fragment_match(hits[0], t):
        kind = 'fragment_discover' if hits[0] == 'discover' else 'fragment_diagnose'
        return _clarify(transcript, norm, VN.question(kind, lang))
    if hits:
        name = hits[0]
        spec = INTENTS[name]
        target = None
        if name in ('ble_scan_via_tv', 'why_disconnect') or name == 'ble_scan_via_phone':
            want = 'phone' if name == 'ble_scan_via_phone' or re.search(r'\b(phone|telephone)\b', t) else 'tv'
            cands = [d['key'] for d in devices if d.get('category') == want]
            if len(cands) != 1:
                reason = f'{len(cands)} {want} device(s) in the graph: choose one on screen'
                return {'intent': name, 'outcome': 'needs_clarification', 'reason': reason,
                        'clarifying_question': reason, 'transcript': transcript,
                        'primitive_id': spec['primitive_id'], 'needs_target': True,
                        'lang': lang, 'normalization': _meta(norm)}
            target = cands[0]
        return {'intent': name, 'outcome': 'proposal', 'primitive_id': spec['primitive_id'],
                'device_key': target or 'fabric', 'requires_consent': spec['consent'],
                'says': spec['says'], 'transcript': transcript, 'also_matched': hits[1:],
                'clarifying_question': None, 'lang': lang, 'normalization': _meta(norm),
                'note': 'Proposal only: review the transcript; nothing runs until you press Run' + (' and consent' if spec['consent'] else '') + '.'}
    if norm['repairs']:
        fixed_hits = [name for name, rx in _P if re.search(rx, fx)]
        if fixed_hits:
            # Two-pass rule: the match needs a repaired token, so this stays
            # a clarification ("did you mean ...?"), never a proposal.
            return _clarify(transcript, norm,
                            VN.repaired_question(fixed_hits[0], lang))
    if VN.is_short(t):
        return _clarify(transcript, norm, VN.question('guidance', lang))
    return {'intent': None, 'outcome': 'unsupported',
            'reason': 'No supported intent recognized; use the buttons or rephrase.',
            'clarifying_question': None, 'transcript': transcript,
            'lang': lang, 'normalization': _meta(norm)}
