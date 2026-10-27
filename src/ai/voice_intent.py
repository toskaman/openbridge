"""Voice/text -> typed intent (V4-10). Deterministic, French + English, no model required.

The transcript is untrusted text. It can only select one of a few typed intents that map to existing primitives;
it never carries a command string, a package name or an address. The result is a *proposal*: the owner reviews the
transcript and the proposal on screen, and execution still goes through the Executor (schema, consent, identity).
Voice is never an authorization factor (no voice biometrics)."""
import re
import unicodedata

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
    t = unicodedata.normalize('NFKD', t.lower())
    return ''.join(c for c in t if not unicodedata.combining(c))


def compile_intent(transcript, devices=()):
    """devices: [{'key','category'}] from the graph. -> proposal dict (never executed here)."""
    if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 400:
        return {'intent': None, 'reason': 'empty or too long transcript'}
    t = _norm(transcript)
    if re.search(REFUSE, t):
        return {'intent': None, 'reason': 'This request needs a manual, explicitly confirmed action; voice cannot start it.', 'transcript': transcript}
    hits = [name for name, rx in _P if re.search(rx, t)]
    if not hits:
        return {'intent': None, 'reason': 'No supported intent recognized; use the buttons or rephrase.', 'transcript': transcript}
    name = hits[0]
    spec = INTENTS[name]
    target = None
    if name in ('ble_scan_via_tv', 'why_disconnect') or name == 'ble_scan_via_phone':
        want = 'phone' if name == 'ble_scan_via_phone' or re.search(r'\b(phone|telephone)\b', t) else 'tv'
        cands = [d['key'] for d in devices if d.get('category') == want]
        if len(cands) != 1:
            return {'intent': name, 'reason': f'{len(cands)} {want} device(s) in the graph: choose one on screen', 'transcript': transcript,
                    'primitive_id': spec['primitive_id'], 'needs_target': True}
        target = cands[0]
    return {'intent': name, 'primitive_id': spec['primitive_id'], 'device_key': target or 'fabric', 'requires_consent': spec['consent'],
            'says': spec['says'], 'transcript': transcript, 'also_matched': hits[1:],
            'note': 'Proposal only: review the transcript; nothing runs until you press Run' + (' and consent' if spec['consent'] else '') + '.'}
