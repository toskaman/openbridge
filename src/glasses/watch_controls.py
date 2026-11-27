"""ENGO 3 / ActiveLook by Microoled — Watch Remote Controls & Live NL Dispatcher.

Provides:
1. Honest Wear OS watch detection (`detect_watches`): detects paired/discovered watches
   reporting `android.hardware.type.watch` / `form=watch`. UI options stay completely hidden
   unless a watch is actually detected.
2. Multi-page <=12-control layouts (`main`, `screens`, `display`, `align`) delivering EVERY
   ENGO 3 control onto the watch Companion via OpenBridge's signed RemoteControls channel
   (`engo_control` B2 skill, hold-to-send safety, live status tile, zero bypass).
3. Deterministic text & voice command matching (`match_engo_watch_command`) so users can
   summon, switch pages, hide controls, or adjust ENGO 3 hardware settings on the fly.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from typing import Any, Optional

from src.adapters import activelook as AL
from src.fabric import relay as fabric_relay

ENGO_WATCH_TOKEN = '__engo_watch_controls__'

ENGO_CONTROL_OPS = (
    'next', 'prev', 'ok', 'back', 'home', 'up', 'down', 'left', 'right',
    'open_screen', 'display_on', 'display_off', 'display_toggle', 'clear',
    'luma_up', 'luma_down', 'luma_set',
    'als_on', 'als_off', 'als_toggle',
    'gesture_on', 'gesture_off', 'gesture_toggle',
    'rotate_on', 'rotate_off', 'rotate_toggle',
    'privacy_cycle', 'privacy_set',
    'lang_toggle', 'lang_set',
    'units_toggle', 'units_set',
    'shift_left', 'shift_right', 'shift_up', 'shift_down', 'shift_reset',
    'inbox_clear', 'status',
    'switch_page', 'hide_controls',
)

PAGE_IDS = ('main', 'screens', 'display', 'align')

# Page catalog: each page has a status header + <= 11 interactive controls (strictly <= 12 total).
_PAGES: dict[str, dict[str, Any]] = {
    'main': {
        'title': {'fr': 'ENGO 3', 'en': 'ENGO 3'},
        'status_label': {'fr': 'ENGO 3', 'en': 'ENGO 3'},
        'items': [
            ({'fr': 'Suivant ▶', 'en': 'Next ▶'}, 'next', None),
            ({'fr': 'Ouvrir (OK)', 'en': 'Open (OK)'}, 'ok', None),
            ({'fr': 'Retour ◀', 'en': 'Back ◀'}, 'back', None),
            ({'fr': 'Accueil ⌂', 'en': 'Home ⌂'}, 'home', None),
            ({'fr': 'Écran ON / OFF', 'en': 'Display ON / OFF'}, 'display_toggle', None),
            ({'fr': 'Luminosité +', 'en': 'Brightness +'}, 'luma_up', None),
            ({'fr': 'Luminosité −', 'en': 'Brightness −'}, 'luma_down', None),
            ({'fr': 'Oracle IA ★', 'en': 'Oracle AI ★'}, 'open_screen', 'oracle'),
            ({'fr': '◧ Tous les écrans', 'en': '◧ All screens'}, 'switch_page', 'screens'),
            ({'fr': '⚙ Optique & Réglages', 'en': '⚙ Optics & Settings'}, 'switch_page', 'display'),
            ({'fr': '✕ Masquer contrôles', 'en': '✕ Hide controls'}, 'hide_controls', None),
        ],
    },
    'screens': {
        'title': {'fr': 'Écrans ENGO 3', 'en': 'ENGO 3 Screens'},
        'status_label': {'fr': 'Écrans', 'en': 'Screens'},
        'items': [
            ({'fr': 'Accueil ⌂', 'en': 'Home ⌂'}, 'open_screen', 'home'),
            ({'fr': 'Messages', 'en': 'Messages'}, 'open_screen', 'inbox'),
            ({'fr': 'Oracle IA ★', 'en': 'Oracle AI ★'}, 'open_screen', 'oracle'),
            ({'fr': 'Assistant Voix', 'en': 'Voice'}, 'open_screen', 'voice'),
            ({'fr': 'Sport', 'en': 'Sport'}, 'open_screen', 'sport'),
            ({'fr': 'Contrôle TV', 'en': 'TV Control'}, 'open_screen', 'tv'),
            ({'fr': 'Aspirateur', 'en': 'Vacuum'}, 'open_screen', 'vacuum'),
            ({'fr': 'Calibration OLED', 'en': 'Calibration'}, 'open_screen', 'calibration'),
            ({'fr': 'Paramètres ENGO', 'en': 'Settings'}, 'open_screen', 'settings'),
            ({'fr': '◀ Essentiels', 'en': '◀ Essentials'}, 'switch_page', 'main'),
            ({'fr': '⚙ Optique & Réglages', 'en': '⚙ Optics & Settings'}, 'switch_page', 'display'),
        ],
    },
    'display': {
        'title': {'fr': 'Optique & Réglages', 'en': 'Optics & Settings'},
        'status_label': {'fr': 'Réglages', 'en': 'Settings'},
        'items': [
            ({'fr': 'Luminosité +', 'en': 'Brightness +'}, 'luma_up', None),
            ({'fr': 'Luminosité −', 'en': 'Brightness −'}, 'luma_down', None),
            ({'fr': 'Auto-Lum (ALS)', 'en': 'Auto-Luma (ALS)'}, 'als_toggle', None),
            ({'fr': 'Tap / Gestes (0x21)', 'en': 'Tap / Gestures'}, 'gesture_toggle', None),
            ({'fr': 'Rotation 180°', 'en': 'Rotate 180°'}, 'rotate_toggle', None),
            ({'fr': 'Confidentialité', 'en': 'Privacy mode'}, 'privacy_cycle', None),
            ({'fr': 'Langue FR / EN', 'en': 'Language FR / EN'}, 'lang_toggle', None),
            ({'fr': 'Unités km / mi', 'en': 'Units km / mi'}, 'units_toggle', None),
            ({'fr': 'Effacer OLED', 'en': 'Clear OLED'}, 'clear', None),
            ({'fr': '⊞ Recalage Optique', 'en': '⊞ Optical Shift'}, 'switch_page', 'align'),
            ({'fr': '◀ Essentiels', 'en': '◀ Essentials'}, 'switch_page', 'main'),
        ],
    },
    'align': {
        'title': {'fr': 'Recalage Optique', 'en': 'Optical Alignment'},
        'status_label': {'fr': 'Optique', 'en': 'Alignment'},
        'items': [
            ({'fr': 'Décaler Gauche ←', 'en': 'Shift Left ←'}, 'shift_left', None),
            ({'fr': 'Décaler Droite →', 'en': 'Shift Right →'}, 'shift_right', None),
            ({'fr': 'Décaler Haut ↑', 'en': 'Shift Up ↑'}, 'shift_up', None),
            ({'fr': 'Décaler Bas ↓', 'en': 'Shift Down ↓'}, 'shift_down', None),
            ({'fr': 'Centrer (Reset)', 'en': 'Center (Reset)'}, 'shift_reset', None),
            ({'fr': 'D-Pad Haut ↑', 'en': 'D-Pad Up ↑'}, 'up', None),
            ({'fr': 'D-Pad Bas ↓', 'en': 'D-Pad Down ↓'}, 'down', None),
            ({'fr': 'Vider Messages', 'en': 'Clear Messages'}, 'inbox_clear', None),
            ({'fr': '◀ Essentiels', 'en': '◀ Essentials'}, 'switch_page', 'main'),
            ({'fr': '⚙ Optique & Réglages', 'en': '⚙ Optics & Settings'}, 'switch_page', 'display'),
            ({'fr': '✕ Masquer contrôles', 'en': '✕ Hide controls'}, 'hide_controls', None),
        ],
    },
}


def _norm(text: str) -> str:
    s = unicodedata.normalize('NFKD', str(text or '').lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', s).strip()


def _is_watch_relay(rid: str, r: dict[str, Any], devices_by_handle: dict[str, dict[str, Any]]) -> Optional[dict[str, Any]]:
    decl = r.get('declared') or {}
    is_watch = decl.get('watch') is True or decl.get('form_factor') == 'watch'
    dev = None
    for h_val in (r.get('device_key'), r.get('address')):
        if h_val and h_val in devices_by_handle:
            dev = devices_by_handle[h_val]
            if dev.get('category') == 'watch':
                is_watch = True
            break
    if not is_watch:
        return None
    return {
        'relay_id': rid,
        'label': (dev or {}).get('label') or r.get('label') or rid,
        'online': bool(r.get('online')),
        'has_remote_controls': 'remote_controls' in (r.get('capabilities') or ()),
        'language': decl.get('language') or 'en',
        'source': 'paired_relay',
    }


def detect_watches(server) -> dict[str, Any]:
    """Detect real paired or discovered Wear OS watches. Never fabricates presence."""
    snap = getattr(server, 'fabric_snapshot', None) or {}
    devs = snap.get('devices') or []
    by_handle: dict[str, dict[str, Any]] = {}
    discovered: list[dict[str, Any]] = []
    for d in devs:
        for hv in (d.get('handles') or {}).values():
            by_handle[hv] = d
        if d.get('category') == 'watch':
            discovered.append({
                'key': d.get('key'),
                'label': d.get('label') or d.get('key'),
                'paired_relay': bool((d.get('handles') or {}).get('COMPANION_RELAY')),
                'online': any(bool(lk.get('online', True)) for lk in (d.get('links') or [])),
            })

    relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
    paired: list[dict[str, Any]] = []
    for rid, r in relays.items():
        row = _is_watch_relay(rid, r, by_handle)
        if row is not None:
            paired.append(row)

    # Sort paired watches: online + remote_controls first
    paired.sort(key=lambda w: (not w['online'], not w['has_remote_controls'], w['relay_id']))
    detected = bool(paired or discovered)
    return {
        'watch_detected': detected,
        'paired_watches': paired,
        'discovered_watches': discovered,
    }


def _pages_for_lang(lang: str) -> list[dict[str, str]]:
    l = 'fr' if lang == 'fr' else 'en'
    return [{'id': pid, 'title': _PAGES[pid]['title'][l]} for pid in PAGE_IDS]


def watch_controls_status(server, lang: str = 'en') -> dict[str, Any]:
    det = detect_watches(server)
    pages_state = dict(getattr(server, '_engo_watch_pages', None) or {})
    default_lang = lang
    if det['paired_watches']:
        default_lang = det['paired_watches'][0].get('language') or lang
    return {
        'partners': ['ENGO', 'ActiveLook by Microoled'],
        'watch_detected': det['watch_detected'],
        'paired_watches': det['paired_watches'],
        'discovered_watches': det['discovered_watches'],
        'active_pages': pages_state,
        'pages': _pages_for_lang(default_lang),
    }


def _pick_watch_relay(server, relay_id: Optional[str] = None) -> dict[str, Any]:
    det = detect_watches(server)
    paired = det['paired_watches']
    if relay_id:
        match = next((w for w in paired if w['relay_id'] == relay_id), None)
        if match is None:
            relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
            if relay_id in relays:
                raise LookupError('Selected Companion is not a detected Wear OS watch')
            raise LookupError('No Wear OS watch paired')
        return match
    if not paired:
        if det['discovered_watches']:
            raise LookupError('Watch detected on network but not paired yet — pair Companion on your watch first')
        raise LookupError('No Wear OS watch detected')
    eligible = [w for w in paired if w['has_remote_controls']]
    if not eligible:
        raise LookupError('Watch Companion lacks remote_controls capability')
    return eligible[0]


def show_watch_controls(
    server,
    relay_id: Optional[str] = None,
    page: str = 'main',
    lang: Optional[str] = None,
    control_port: int = 7791,
) -> dict[str, Any]:
    """Install a <=12-control ENGO 3 page onto the detected Wear OS watch via RemoteControls."""
    from src.runtime.api_v2 import remote_controls
    from src.runtime.remote_controls import _key_fp

    w = _pick_watch_relay(server, relay_id)
    rid = w['relay_id']
    p_id = page if page in _PAGES else 'main'
    eff_lang = (lang or w.get('language') or 'en')
    eff_lang = 'fr' if str(eff_lang).lower().startswith('fr') else 'en'
    spec = _PAGES[p_id]

    rc = remote_controls(server)
    relay = rc._relay(rid)
    with rc._lock:
        rc.generation += 1
        gen = rc.generation
    fp = _key_fp(relay['key'])

    out: dict[str, Any] = {}
    for labels, op, val in spec['items']:
        lbl = labels[eff_lang][:40]
        params: dict[str, Any] = {'op': op}
        if val is not None:
            params['value'] = str(val)
        if op == 'switch_page':
            params['relay_id'] = rid
        digest = hashlib.sha256(
            json.dumps([rid, 'engo_control', params, lbl], sort_keys=True).encode()
        ).hexdigest()[:10]
        cid = f'ctl-{digest}-g{gen}'
        out[cid] = {
            'label': lbl,
            'skill_id': 'engo_control',
            'target': None,
            'params': params,
            'generation': gen,
            'key_fp': fp,
            'ui_kind': 'button',
        }

    # Live status header widget (kind='status' counts toward MAX_CONTROLS=12 -> 1 status + 11 buttons <= 12)
    summary = _current_engo_status(server, control_port=control_port) or spec['title'][eff_lang]
    st_id = f'ui-engo-{p_id[:8]}-g{gen}'
    shown = {
        st_id: {
            'kind': 'status',
            'label': spec['status_label'][eff_lang],
            'value': summary[:fabric_relay.MAX_STATUS_TEXT],
            'source': None,
        }
    }

    rc._install(rid, gen, fp, out, shown=shown, revision=(gen % 100000) or 1)
    pages_map = getattr(server, '_engo_watch_pages', None)
    if pages_map is None:
        server._engo_watch_pages = pages_map = {}
    pages_map[rid] = p_id
    return {
        'ok': True,
        'partners': ['ENGO', 'ActiveLook by Microoled'],
        'relay_id': rid,
        'watch': w['label'],
        'page': p_id,
        'title': spec['title'][eff_lang],
        'controls_count': len(out),
        'lang': eff_lang,
    }


def hide_watch_controls(server, relay_id: Optional[str] = None) -> dict[str, Any]:
    """Remove ENGO 3 controls cleanly from the detected Wear OS watch."""
    from src.runtime.api_v2 import remote_controls
    from src.runtime.remote_controls import _key_fp

    w = _pick_watch_relay(server, relay_id)
    rid = w['relay_id']
    rc = remote_controls(server)
    relay = rc._relay(rid)
    with rc._lock:
        rc.generation += 1
        gen = rc.generation
    fp = _key_fp(relay['key'])
    rc._install(rid, gen, fp, {}, shown={})
    pages_map = getattr(server, '_engo_watch_pages', None)
    if isinstance(pages_map, dict):
        pages_map.pop(rid, None)
    return {'ok': True, 'relay_id': rid, 'watch': w['label'], 'hidden': True}


def _current_engo_status(server, control_port: int = 7791) -> Optional[str]:
    hub = getattr(server, 'glasses_hub', None)
    if hub is not None and hasattr(hub, 'control_summary'):
        return hub.control_summary()
    try:
        from src.glasses.cli import send as glasses_send
        res = glasses_send({'engo_control': {'op': 'status'}}, port=control_port, timeout=0.4)
        if isinstance(res, dict) and res.get('status'):
            return str(res['status'])
    except Exception:
        pass
    return None


def _ble_fallback_packet(op: str, value: Any = None) -> Optional[bytes]:
    """Best-effort raw ActiveLook BLE packet when no `glasses run` Hub is active."""
    if op == 'clear':
        return AL.cmd_clear()
    if op == 'display_on':
        return AL.cmd_power(True)
    if op == 'display_off':
        return AL.cmd_power(False) + AL.cmd_clear()
    if op == 'luma_set' and value is not None:
        return AL.cmd_luma(int(value))
    if op == 'als_on':
        return AL.cmd_als_enable(True)
    if op == 'als_off':
        return AL.cmd_als_enable(False)
    if op == 'gesture_on':
        return AL.encode_packet(0x20, b'\x01') + AL.cmd_gesture_enable(True)
    if op == 'gesture_off':
        return AL.cmd_gesture_enable(False)
    if op == 'shift_reset':
        return AL.cmd_shift(0, 0)
    return None


def _send_ble_via_phone_relay(server, pkt: bytes) -> Optional[str]:
    relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
    for rid, r in relays.items():
        if 'glasses_link' not in (r.get('capabilities') or ()) or not r.get('online'):
            continue
        try:
            msg = fabric_relay.command(r['key'], rid, 'glasses_write', {'chunks': [base64.b64encode(pkt).decode('ascii')]})
            rep = fabric_relay.verify(r['key'], r['send'](r, msg), r['seen']).get('params') or {}
            if rep.get('accepted', 0) > 0:
                return rid
        except Exception:
            continue
    return None


def execute_engo_action(
    server,
    params: dict[str, Any],
    relay_id: Optional[str] = None,
    control_port: int = 7791,
) -> tuple[str, Optional[str], str, bool, dict[str, Any]]:
    """Run one validated `engo_control` invocation and return Executor 5-tuple."""
    op = str(params.get('op') or '').strip().lower()
    val = params.get('value')
    target_rid = params.get('relay_id') or relay_id
    if op not in ENGO_CONTROL_OPS:
        raise ValueError(f'UNKNOWN_ENGO_OP: {op}')

    if op == 'switch_page':
        p = str(val or 'main')
        res = show_watch_controls(server, relay_id=target_rid, page=p, control_port=control_port)
        return 'EXECUTED', None, f"Page {res['title']}", True, res

    if op == 'hide_controls':
        res = hide_watch_controls(server, relay_id=target_rid)
        return 'EXECUTED', None, 'ENGO controls hidden from watch', True, res

    hub = getattr(server, 'glasses_hub', None)
    if hub is not None and hasattr(hub, 'apply_control'):
        out = hub.apply_control(op, val)
        summary = out.get('summary') or out.get('status') or op
        return 'EXECUTED', None, str(summary), True, out

    try:
        from src.glasses.cli import send as glasses_send
        port = int(params.get('control_port') or control_port)
        out = glasses_send({'engo_control': {'op': op, 'value': val}}, port=port, timeout=1.5)
        if isinstance(out, dict) and not out.get('error'):
            summary = out.get('summary') or out.get('status') or op
            return 'EXECUTED', None, str(summary), True, out
    except Exception:
        pass

    pkt = _ble_fallback_packet(op, val)
    if pkt is not None:
        used_rid = _send_ble_via_phone_relay(server, pkt)
        if used_rid is not None:
            return 'EXECUTED_UNVERIFIED', None, f'ENGO BLE {op} sent via {used_rid}', False, {'op': op, 'relay_id': used_rid}

    raise ValueError('ENGO_UNAVAILABLE: ENGO 3 hub is not running (`openbridge glasses run`)')


# ---- Deterministic NL / voice command parser for on-the-fly ENGO Watch activation

_SHOW_RX = re.compile(
    r'\b(affiche\w*|montre[rz]?\w*|mets|mettez|mettre|ajoute\w*|active\w*|ouvre|ouvrir|donne\w*|'
    r'show|display|put|open|add|enable|launch|send)\b'
)
_WATCH_NOUN_RX = re.compile(r'\b(la|ma|ta|sa|une|cette)\s+montres?\b')
_HIDE_RX = re.compile(
    r'\b(cache\w*|masque\w*|enleve\w*|retire\w*|supprime\w*|ferme\w*|desactive\w*|efface\w*|'
    r'hide|remove|clear|close|disable)\b'
)
_WATCH_RX = re.compile(r'\b(montre|watch|wear\s*os|smartwatch|poignet|wrist)\b')
_ENGO_RX = re.compile(r'\b(engo\s*3?|lunettes?|glasses|activelook|hud)\b')
_CONTROLS_RX = re.compile(r'\b(controles?|commandes?|boutons?|panneau|menu|tous|reglages?|controls?|buttons?|panel|remotes?)\b')

_SCREEN_KEYWORDS = {
    'oracle': 'oracle',
    'ia': 'oracle',
    'messages': 'inbox',
    'inbox': 'inbox',
    'notifications': 'inbox',
    'sport': 'sport',
    'course': 'sport',
    'velo': 'sport',
    'tv': 'tv',
    'tele': 'tv',
    'aspirateur': 'vacuum',
    'vacuum': 'vacuum',
    'robot': 'vacuum',
    'calibration': 'calibration',
    'calibrage': 'calibration',
    'parametres': 'settings',
    'settings': 'settings',
    'voix': 'voice',
    'voice': 'voice',
    'accueil': 'home',
    'home': 'home',
}


def match_engo_watch_command(text: str, lang_hint: Optional[str] = None, from_watch: bool = False) -> Optional[dict[str, Any]]:
    """Parse text/voice command targeting ENGO 3 watch controls or direct ENGO actions.

    Returns None when the utterance is unrelated, else a structured command dict:
      {'kind': 'watch_panel', 'action': 'show'|'hide'|'toggle', 'page': ..., 'lang': ...}
    or
      {'kind': 'engo_direct', 'op': ..., 'value'?: ..., 'lang': ...}
    """
    raw = str(text or '').strip()
    if raw.startswith(ENGO_WATCH_TOKEN):
        rest = raw[len(ENGO_WATCH_TOKEN):].lstrip(':')
        if rest == 'hide':
            return {'kind': 'watch_panel', 'action': 'hide', 'page': 'main', 'lang': lang_hint or 'en'}
        if rest.startswith('page:'):
            pg = rest.split(':', 1)[1]
            return {'kind': 'watch_panel', 'action': 'show', 'page': pg if pg in PAGE_IDS else 'main', 'lang': lang_hint or 'en'}
        act = 'toggle' if rest == 'toggle' else 'show'
        return {'kind': 'watch_panel', 'action': act, 'page': 'main', 'lang': lang_hint or 'en'}

    s = _norm(raw)
    if not s:
        return None
    fr_hints = bool(re.search(r'\b(montre|lunettes|affiche|mets|cache|masque|enleve|ecrans?|luminosite|reglages|desactive|retourne|eteins|allume)\b', s))
    lang = 'fr' if (lang_hint == 'fr' or fr_hints) else 'en'

    has_engo = bool(_ENGO_RX.search(s))
    has_watch = bool(_WATCH_RX.search(s)) or from_watch
    has_controls = bool(_CONTROLS_RX.search(s))
    s_verbs = _WATCH_NOUN_RX.sub(' watch ', s)
    has_show = bool(_SHOW_RX.search(s_verbs))
    has_hide = bool(_HIDE_RX.search(s_verbs))

    # 1) Direct watch panel show / hide / page switch when mentioning ENGO + controls (or from watch)
    if has_engo and (has_controls or has_watch):
        if has_hide and not has_show:
            # Disambiguate "éteins / masque l'écran ENGO" vs "masque les contrôles ENGO"
            if has_controls or 'montre' in s or 'watch' in s:
                return {'kind': 'watch_panel', 'action': 'hide', 'page': 'main', 'lang': lang}
        if has_show or (has_controls and has_watch):
            page = 'main'
            if re.search(r'\b(ecrans?|screens?)\b', s):
                page = 'screens'
            elif re.search(r'\b(align\w*|recal\w*|decal\w*|shift|optique)\b', s):
                page = 'align'
            elif re.search(r'\b(lum\w*|bright\w*|als|rotat\w*|priva\w*|confiden\w*|reglag\w*|setting\w*|capteur\w*|sensor\w*)\b', s):
                page = 'display'
            if has_watch or has_controls:
                return {'kind': 'watch_panel', 'action': 'show', 'page': page, 'lang': lang}

    # 2) Direct ENGO 3 hardware/display commands by text/voice (only when ENGO/glasses/lunettes named)
    if has_engo:
        m_lum = re.search(r'\b(luminosit\w*|brightness|luma)\b.*?\b([0-9]|1[0-5])\b', s)
        if m_lum:
            return {'kind': 'engo_direct', 'op': 'luma_set', 'value': str(int(m_lum.group(2))), 'lang': lang}
        if re.search(r'\b(luminosit\w*|brightness|luma)\b', s):
            if re.search(r'\b(plus|monte\w*|augment\w*|up|higher|increas\w*)\b', s):
                return {'kind': 'engo_direct', 'op': 'luma_up', 'lang': lang}
            if re.search(r'\b(moins|baiss\w*|diminu\w*|down|lower|decreas\w*)\b', s):
                return {'kind': 'engo_direct', 'op': 'luma_down', 'lang': lang}
        if re.search(r'\b(auto.?lum\w*|als)\b', s):
            op = 'als_off' if re.search(r'\b(desactiv\w*|coupe\w*|off|disable)\b', s) else 'als_on'
            return {'kind': 'engo_direct', 'op': op, 'lang': lang}
        if re.search(r'\b(rotat\w*|retourn\w*|pivot\w*|flip|180)\b', s):
            return {'kind': 'engo_direct', 'op': 'rotate_toggle', 'lang': lang}
        if re.search(r'\b(etein\w*|coupe\w*|turn off|power off|sleep)\b', s):
            return {'kind': 'engo_direct', 'op': 'display_off', 'lang': lang}
        if re.search(r'\b(allume\w*|turn on|power on|wake)\b', s):
            return {'kind': 'engo_direct', 'op': 'display_on', 'lang': lang}
        if re.search(r'\b(clear|efface\w*|vide\w*)\b', s):
            return {'kind': 'engo_direct', 'op': 'clear', 'lang': lang}
        if re.search(r'\b(ouvre|ouvrir|open|affiche\w*|show)\b', s):
            for kw, scr in _SCREEN_KEYWORDS.items():
                if re.search(rf'\b{re.escape(kw)}\b', s):
                    return {'kind': 'engo_direct', 'op': 'open_screen', 'value': scr, 'lang': lang}

    return None


def apply_engo_watch_order(
    server,
    order: dict[str, Any],
    source_relay_id: Optional[str] = None,
) -> dict[str, Any]:
    """Execute a parsed watch-panel or direct ENGO order and return bilingual status reply."""
    lang = 'fr' if order.get('lang') == 'fr' else 'en'
    if order['kind'] == 'watch_panel':
        target_rid = None
        if source_relay_id:
            det = detect_watches(server)
            if any(w['relay_id'] == source_relay_id for w in det['paired_watches']):
                target_rid = source_relay_id
        action = order['action']
        page = order.get('page', 'main')
        try:
            if action == 'toggle':
                cur = (getattr(server, '_engo_watch_pages', None) or {}).get(target_rid or _pick_watch_relay(server)['relay_id'])
                res = hide_watch_controls(server, relay_id=target_rid) if cur else show_watch_controls(server, relay_id=target_rid, page=page, lang=lang)
            elif action == 'hide':
                res = hide_watch_controls(server, relay_id=target_rid)
            else:
                res = show_watch_controls(server, relay_id=target_rid, page=page, lang=lang)
        except (LookupError, Exception) as e:
            return {'ok': False, 'status': 'escalation_required', 'text': str(e)[:160]}
        if res.get('hidden'):
            txt = 'Contrôles ENGO 3 masqués sur la montre.' if lang == 'fr' else 'ENGO 3 controls hidden from watch.'
        else:
            txt = (f"Contrôles ENGO 3 affichés sur {res['watch']} ({res['title']})."
                   if lang == 'fr' else f"ENGO 3 controls shown on {res['watch']} ({res['title']}).")
        return {'ok': True, 'status': 'resolved', 'text': txt, 'result': res}

    # Direct ENGO hardware/navigation command
    try:
        _, summary, msg, _, data = execute_engo_action(server, {'op': order['op'], 'value': order.get('value')})
        return {'ok': True, 'status': 'resolved', 'text': msg, 'result': data}
    except Exception as e:
        return {'ok': False, 'status': 'escalation_required', 'text': str(e)[:160]}
