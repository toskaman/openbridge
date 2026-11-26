"""Optional Companion modules: features the owner switches on or off per paired screen.

Today one module, the Oracle (ask a question out loud on the phone or watch, the answer shows on the ENGO glasses).
The switch lives on the device (relay op ``set_modules``) so the Companion hides what is off; the PC asks for the
change from three places, all owner actions: the Companions customisation screen, the CLI
(``openbridge glasses module oracle on|off``) and a typed or spoken order on the Companion ("désactive l'Oracle").
"""
import re
import unicodedata

from src.fabric import relay as fabric_relay

MODULES = {'oracle': 'Oracle: ask a question out loud, the answer shows on the glasses'}

_ON = r"(?:active|activez|activer|allume|allumez|ajoute|ajoutez|mets|remets|affiche|enable|turn on|switch on|add|show)"
_OFF = r"(?:desactive|desactivez|desactiver|eteins|eteignez|enleve|enlevez|retire|retirez|supprime|supprimez|cache|"
_OFF += r"masque|disable|turn off|switch off|remove|hide)"
_TOGGLE = re.compile(r"^\s*(?:(?P<on>%s)|(?P<off>%s))\s+(?:les |le |la |l'|l |the )?(?:module )?(?P<m>[a-z']+)" % (_ON, _OFF))


def _module_word(word):
    """'oracle', and what speech-to-text makes of it ('loracle', 'oracles', 'lauracle'...)."""
    import difflib
    w = word.strip("'").removeprefix("l'")
    for name in MODULES:
        if w == name or difflib.SequenceMatcher(None, w, name).ratio() >= 0.75 \
                or difflib.SequenceMatcher(None, w.removeprefix('l'), name).ratio() >= 0.75:
            return name
    return None


def _plain(text):
    t = unicodedata.normalize('NFKD', str(text or '').lower())
    return ''.join(c for c in t if not unicodedata.combining(c)).replace('\u2019', "'")


def parse_toggle(text):
    """'désactive l'Oracle' -> ('oracle', False); anything else -> None. Deterministic: no model involved."""
    m = _TOGGLE.match(_plain(text))
    if not m:
        return None
    name = _module_word(m.group('m'))
    return (name, m.group('on') is not None) if name else None


def _send(server, rid, op, params=None):
    from src.runtime.companion_commands import companion_commands
    return companion_commands(server)._send(rid, op, params)


def _relays(server):
    return getattr(getattr(server, 'relays', None), 'relays', None) or {}


def state(server):
    """Modules of every paired Companion, read live with a signed get_status (offline ones are marked so)."""
    screens = {}
    for rid, r in list(_relays(server).items()):
        doc = {'online': bool(r.get('online')), 'modules': None}
        if r.get('online'):
            try:
                st = _send(server, rid, 'get_status')
                if isinstance(st.get('modules'), dict):
                    doc['modules'] = {k: bool(v) for k, v in st['modules'].items() if k in MODULES}
            except fabric_relay.RelayError:
                doc['online'] = False
        screens[rid] = doc
    return {'modules': MODULES, 'screens': screens}


def set_module(server, rid, module, enabled):
    if module not in MODULES:
        raise ValueError('unknown module: %s' % module)
    if rid not in _relays(server):
        raise ValueError('unknown or unpaired screen: %s' % rid)
    reply = _send(server, rid, 'set_modules', {module: bool(enabled)})
    mods = reply.get('modules') if isinstance(reply.get('modules'), dict) else {}
    if mods.get(module) is not bool(enabled):
        raise fabric_relay.RelayError('The Companion did not confirm the change (update it to 0.14.0 or later)')
    return {'relay_id': rid, 'module': module, 'enabled': bool(enabled)}
