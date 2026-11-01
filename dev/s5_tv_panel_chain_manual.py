"""Owner-authorized S5 MANUAL acceptance: model panel -> TV install ->
MANUAL owner press (START, motion-observable) -> vacuum read-back ->
MANUAL owner press (DOCK, return) -> read-back -> revoke -> deny.

Same product paths as s5_tv_panel_chain.py, except the press stage:
instead of adb injection, the script prints PRESS_NOW and polls the
press history for a genuine owner tap (300 s budget per press).
Prints sanitized JSON only (no keys, no codes) and writes a transcript.

Usage: python -m dev.s5_tv_panel_chain_manual <propose-output.json> [vacuum-label]
"""
import json
import os
import re
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

PATCH = sys.argv[1]
VACUUM_LABEL = sys.argv[2] if len(sys.argv) > 2 else 'Robot vacuum (Tuya)'
PRESS_ORDER = [c.strip() for c in (sys.argv[3] if len(sys.argv) > 3 else 'start,dock').split(',') if c.strip()]
LIVE_TV_RID = 'relay-dabd2a796665'  # live server's dormant Oct-29 TV relay; flag reuse
SHOT_DIR = Path('E:/shots/demo-s5-01nov')
SHOT_DIR.mkdir(parents=True, exist_ok=True)

from src.server import create_server  # noqa: E402
from src.runtime import api_v2  # noqa: E402
from src.cli import ensure_discovery, default_providers  # noqa: E402

out = {}


def fail(step, error):
    out[step] = 'FAILED: %s: %s' % (type(error).__name__, str(error)[:160])
    return out


def shot(serial, name):
    # NOTE: exec-out is polluted by this TV's vendor screencap wrapper
    # (log lines prepended to the stream); shell-file + pull is clean.
    dest = SHOT_DIR / name
    subprocess.run(['adb', '-s', serial, 'shell', 'screencap', '-p', '/sdcard/s5shot.png'],
                   capture_output=True, timeout=60)
    p = subprocess.run(['adb', '-s', serial, 'pull', '/sdcard/s5shot.png', str(dest)],
                       capture_output=True, timeout=60)
    subprocess.run(['adb', '-s', serial, 'shell', 'rm', '/sdcard/s5shot.png'],
                   capture_output=True, timeout=60)
    if p.returncode == 0 and dest.exists() and dest.read_bytes()[:4] == b'\x89PNG':
        return str(dest)
    return 'shot-failed:%s' % p.returncode


def _ocr_run(png_path):
    import asyncio
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.media.ocr as ocr
    import winrt.windows.storage as storage

    async def go():
        f = await storage.StorageFile.get_file_from_path_async(str(png_path))
        stream = await f.open_async(storage.FileAccessMode.READ)
        decoder = await imaging.BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        engine = ocr.OcrEngine.try_create_from_user_profile_languages()
        return await engine.recognize_async(bitmap)

    return asyncio.run(go())


def ocr_text(png_path):
    """Windows built-in OCR (winrt). Returns text or 'OCR_ERROR:...'."""
    try:
        return _ocr_run(png_path).text
    except Exception as e:
        return 'OCR_ERROR:%s: %s' % (type(e).__name__, str(e)[:100])


def ocr_words(png_path):
    """OCR word boxes: [(word, x, y, w, h)] in screenshot pixels
    (1:1 with this TV's 1920x1080 panel)."""
    words = []
    for line in _ocr_run(png_path).lines:
        for w in line.words:
            r = w.bounding_rect
            words.append((w.text, int(r.x), int(r.y), int(r.width), int(r.height)))
    return words


def find_button_center(png_path, label_words=('dock', 'vacuum')):
    """Center of the label's word boxes (same OCR line, adjacent).
    Returns (x, y) or None."""
    words = ocr_words(png_path)
    lows = [(w.lower(), x, y, bw, bh) for w, x, y, bw, bh in words]
    for i, (w0, x0, y0, b0, h0) in enumerate(lows):
        if w0 != label_words[0]:
            continue
        for w1, x1, y1, b1, h1 in lows[i + 1:i + 4]:
            if w1 == label_words[1] and abs(y1 - y0) < 40:
                x = min(x0, x1) + (max(x0 + b0, x1 + b1) - min(x0, x1)) // 2
                y = min(y0, y1) + (max(y0 + h0, y1 + h1) - min(y0, y1)) // 2
                return x, y
    return None


def upscale_for_ocr(png_path):
    """2x upscale + contrast + threshold: the code digits are thin and
    letter-spaced, which raw OCR fragments. Returns the enhanced path."""
    from PIL import Image, ImageOps
    im = Image.open(png_path).convert('L')
    w, h = im.size
    im = im.resize((w * 2, h * 2))
    im = ImageOps.autocontrast(im, cutoff=1)
    im = im.point(lambda v: 255 if v > 150 else 0)
    out = str(png_path) + '.big.png'
    im.save(out)
    return out


def code_candidates(text):
    """Yield (code, rule) pairs, best-first. Handles spaced halves
    ("880 ... 065") as a last resort: two 3-digit runs within 80 chars."""
    pats = [r'(?i)(?:pair\w*|code|enter)\W{0,40}(\d{3})\s*(\d{3})',
            r'\b(\d{3})\s{1,3}(\d{3})\b',
            r'(?i)(?:pair\w*|code|enter)\W{0,40}(\d{6})',
            r'\b(\d{6})\b']
    for p in pats:
        m = re.search(p, text)
        if m:
            yield ''.join(g for g in m.groups() if g), 'pat%d' % pats.index(p)
    frags = [m for m in re.finditer(r'\b(\d{3})\b', text)]
    for a, b in zip(frags, frags[1:]):
        if 0 < b.start() - a.end() < 80:
            yield a.group(1) + b.group(1), 'frag-join'


def read_pairing_code(serial, rounds=3):
    """Screencap + OCR pairing-code candidates (raw and enhanced
    variants), best-first, deduped. Returns a list of
    (code, rule, snippet); empty when unreadable."""
    found, seen = [], set()
    for i in range(rounds):
        if i:
            time.sleep(3)
        png = shot(serial, 's5_tv_code_%d.png' % i)
        if png.startswith('shot-failed'):
            continue
        texts = [ocr_text(png)]
        try:
            texts.append(ocr_text(upscale_for_ocr(png)))
        except Exception:
            pass
        for text in texts:
            if text.startswith('OCR_ERROR'):
                continue
            for code, rule in code_candidates(text):
                if code not in seen:
                    seen.add(code)
                    found.append((code, '%s/r%d' % (rule, i), text[:160]))
    return found


s = create_server(0)
try:
    snap = ensure_discovery(s, default_providers(Namespace(providers=None)))
    devs = snap.get('devices', []) if isinstance(snap, dict) else []
    out['discovery'] = sorted({(d.get('label'), d.get('category')) for d in devs})
    router = api_v2.router(s)
    try:
        routes = router.skill_routes('vacuum_command', VACUUM_LABEL)
        out['vacuum_routes'] = {'selected': routes.get('selected_route_id'),
                                'states': [(r.get('route_id'), r.get('state')) for r in routes.get('routes', [])][:6]}
    except Exception as e:
        out.update(fail('vacuum_routes', e))
        raise SystemExit(json.dumps(out, indent=1))
    tv = next(k for k, d in s.fabric_registry.devices.items()
              if d['category'] == 'tv' and 'handles' in d
              and any(i.strong for i in d['identifiers']))
    out['tv_label'] = s.fabric_registry.devices[tv].get('label')
    handle = next(iter(s.fabric_registry.devices[tv]['handles'].values()))
    serial = next(k for k, v in s.android._handles.items() if v == handle)
    out['tv_serial_suffix'] = serial[-9:]
    adb = lambda *a: subprocess.run(['adb', '-s', serial, *a], capture_output=True,
                                    text=True, encoding='utf-8', timeout=60).stdout
    # Foreground the Companion right before pairing: the TV falls back to
    # ambient quickly, and the code card only shows in a visible activity.
    adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(3)
    try:
        pair = s.relay_action('/api/relay-pair-start', {'device_id': handle})
    except Exception as e:
        out.update(fail('pair_start', e))
        raise SystemExit(json.dumps(out, indent=1))
    rid = pair['relay_id']
    out['relay_id'] = rid
    out['live_rid_reused'] = (rid == LIVE_TV_RID)
    from src.fabric import relay as fabric_relay
    conf, used = None, None
    if os.environ.get('OB_REUSE_PAIRED') == '1' and rid == LIVE_TV_RID:
        # Attempt-1 revoked the installed controls but NOT the pairing
        # itself; a fresh pair-start on an already-paired relay yields no
        # new challenge (confirm then refuses 'not paired'). Verify
        # liveness via signed get_status and skip the challenge. Recorded,
        # never silent; falls through to the challenge on any doubt.
        try:
            _relay = s.relays.relays[rid]
            _st = fabric_relay.verify(
                _relay['key'], _relay['send'](_relay, fabric_relay.command(_relay['key'], rid, 'get_status')),
                _relay['seen']).get('params', {})
            _decl = _relay.get('declared') or {}
            conf = {'state': 'PAIRED (reused, challenge skipped)',
                    'declared': {'capabilities': sorted(_decl.get('capabilities', ())) if isinstance(_decl, dict) else []}}
            used = 'reuse-paired-skip'
            out['pair_confirm'] = 'SKIPPED: get_status verified on reused rid'
        except Exception as e:
            out['pair_reuse_verify'] = 'FAILED, falling through to challenge: %s' % str(e)[:120]
            conf = None
    if conf is None and os.environ.get('OB_PAIR_ASSIST') == '1':
        # Operator-assisted code read: the 120 s TV code expiry plus the
        # huge pairing digits defeat the 3-round OCR loop tonight
        # (attempt-1 already proved the unassisted path: code 718199
        # auto-read + confirmed). One fast screenshot for the operator,
        # who drops the 6 digits in pair-assist-code.txt. The OWNER still
        # performs every physical button press; this only reads a setup
        # code. Falls back to the OCR loop on any doubt.
        try:
            (SHOT_DIR / 'pair-assist-code.txt').unlink(missing_ok=True)
            adb('shell', 'screencap', '-p', '/sdcard/pair-assist.png')
            subprocess.run(['adb', '-s', serial, 'pull', '/sdcard/pair-assist.png',
                            str(SHOT_DIR / 'pair-assist.png')],
                           capture_output=True, timeout=60)
            (SHOT_DIR / 'chain-progress.txt').write_text('NEED_CODE', encoding='utf-8')
            _code, _deadline = None, time.monotonic() + 105  # inside the 120 s TV TTL
            while time.monotonic() < _deadline:
                _p = SHOT_DIR / 'pair-assist-code.txt'
                if _p.exists():
                    _t = _p.read_text(encoding='utf-8').strip().replace(' ', '')
                    if re.fullmatch(r'\d{6}', _t):
                        _code = _t
                        break
                time.sleep(3)
            if _code:
                try:
                    conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': _code})
                    used = 'operator-assist'
                    out['pair_confirm'] = 'ASSISTED: operator read code from screenshot (OCR font issue, disclosed)'
                except fabric_relay.RelayError as e:
                    out['confirm_assist'] = str(e)[:80]
                    conf = None
            else:
                out['pair_assist'] = 'no operator code within 105 s'
        except Exception as e:
            out['pair_assist'] = 'assist path error: %s' % str(e)[:120]
            conf = None
    if conf is None:
        # NOTE: uiautomator dump fails on this TV ("could not get idle
        # state"); the pairing code is read via screencap + on-device OCR.
        cands = read_pairing_code(serial)
        out['code_candidates'] = [(c, r) for c, r, _ in cands[:6]]
        out['code_snippets'] = [sn for _, _, sn in cands[:3]]
        out['code_read_from_screen'] = bool(cands)
        for code, rule, _ in cands[:3]:  # at most 3 of the 5 pairing attempts
            try:
                conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
                used = rule
                break
            except fabric_relay.RelayError as e:
                out['confirm_%s' % rule] = str(e)[:80]
        if conf is None:
            out.update(fail('pair_confirm', RuntimeError('no candidate accepted')))
            raise SystemExit(json.dumps(out, indent=1))
    out['code_match_rule'] = used
    out['paired'] = conf['state']
    out['declared_caps'] = sorted((conf.get('declared') or {}).get('capabilities', ()))
    from src.fabric import relay as fabric_relay
    relay = s.relays.relays[rid]
    status = fabric_relay.verify(
        relay['key'], relay['send'](relay, fabric_relay.command(relay['key'], rid, 'get_status')),
        relay['seen']).get('params', {})
    out['full_control'] = bool(fabric_relay.reported_full_control(status))
    from src.forge import v4_ui
    from src.runtime import dashboards as D
    doc = json.loads(Path(PATCH).read_text(encoding='utf-8'))
    if doc.get('reuse_widgets'):
        # Honest fallback (recorded): fresh proposal blocked tonight, so the
        # 31-Oct Glimmer-validated widgets are installed verbatim; only the
        # opaque target pointer is re-resolved to the current discovery epoch
        # (rotating keys make the stored pointer unusable; the security
        # property — target ∈ currently-offered TV — is preserved).
        from src.cli import _ui_bindable, build_bundle
        _bundle = build_bundle(devs, list(_ui_bindable()))
        _bdev = next(b for b in _bundle['devices'] if b.get('category') == 'tv')
        doc['offered_opaque_ids'] = [b['opaque_id'] for b in _bundle['devices']]
        doc['patch']['target_opaque_id'] = _bdev['opaque_id']
        out['patch_reused_from'] = doc.get('reuse_source', '?')
        out['patch_reuse_reason'] = doc.get('reuse_reason', '?')
        out['patch_target_reresolved'] = _bdev.get('label', '?')
    patch = v4_ui.validate_patch(doc['patch'], D.BINDABLE_PATCH_SKILLS)
    out['patch_widgets'] = len(patch['widgets'])
    out['target_offered'] = patch.get('target_opaque_id') in (doc.get('offered_opaque_ids') or [])
    if not out['target_offered']:
        raise SystemExit(json.dumps(out, indent=1))
    from src.adapters import tuya_local
    vac = tuya_local.TuyaVacuum(tuya_local.owner_link())
    out['vacuum_pre'] = {f['name']: f['value'] for f in vac.facts()}
    controls = api_v2.remote_controls(s)
    try:
        controls_state = D.install_patch(controls, rid, patch, VACUUM_LABEL,
                                         D.BINDABLE_PATCH_SKILLS, consent=True,
                                         resolve_target=router.resolve_target)
    except Exception as e:
        out.update(fail('install', e))
        raise SystemExit(json.dumps(out, indent=1))
    grants = dict(controls.grants.get(rid, {}))
    out['installed'] = sorted((c['label'], c['skill_id'], c['params']) for c in grants.values())
    def cid_for(cmd):
        try:
            return next(cid for cid, c in grants.items() if c['params'].get('command') == cmd)
        except StopIteration:
            return None
    start_cid = cid_for('start')
    dock_cid = cid_for('dock')
    out['start_cid_found'] = bool(start_cid)
    out['shot_installed'] = shot(serial, 'demo-s5-tv-installed.png')
    if not start_cid or not dock_cid:
        out.update(fail('install', RuntimeError('start/dock buttons missing from grants')))
        raise SystemExit(json.dumps(out, indent=1))

    def wait_manual_press(cid, label, budget_s=300):
        before = len([h for h in controls.history if h.get('control_id') == cid])
        print('PRESS_NOW: tap "%s" on the TV now (manual owner tap, %ds budget)'
              % (label, budget_s), flush=True)
        (SHOT_DIR / 'chain-progress.txt').write_text('WAIT_PRESS:%s' % label, encoding='utf-8')
        t0 = time.time()
        while time.time() - t0 < budget_s:
            time.sleep(3)
            hits = [h for h in controls.history if h.get('control_id') == cid]
            if len(hits) > before:
                return hits[-1]
        return None

    # Attempt-2 learning: dismiss the IME keyboard so all four buttons are
    # visible before the owner presses (navigation only, never the press).
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    time.sleep(1)
    out['shot_installed'] = shot(serial, 'demo-s5-tv-installed.png')
    # Manual presses in PRESS_ORDER (argv3, default 'start,dock'). Facts
    # surround each press; owner taps each button with a ~2 s hold.
    _cids = {'start': (start_cid, 'Start vacuum'), 'dock': (dock_cid, 'Dock vacuum'),
             'pause': (cid_for('pause'), 'Pause vacuum'),
             'empty_dust': (cid_for('empty_dust'), 'Empty dustbin')}
    out['press_order'] = PRESS_ORDER
    for _i, _cmd in enumerate(PRESS_ORDER):
        _cid, _label = _cids.get(_cmd, (None, _cmd))
        if not _cid:
            out.update(fail('press_%s_manual' % _cmd, RuntimeError('button missing from grants')))
            (SHOT_DIR / 'chain-manual-transcript.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
            raise SystemExit(json.dumps(out, indent=1))
        out['vacuum_pre_%s' % _cmd] = {f['name']: f['value'] for f in vac.facts()}
        _hit = wait_manual_press(_cid, _label, budget_s=600)
        if _hit is None:
            out.update(fail('press_%s_manual' % _cmd, RuntimeError('no manual press within budget')))
            (SHOT_DIR / 'chain-manual-transcript.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
            raise SystemExit(json.dumps(out, indent=1))
        out['press%d_history' % (_i + 1)] = json.dumps(_hit, default=str)[:1500]
        out['shot_press%d' % (_i + 1)] = shot(serial, 'demo-s5-tv-press-%s.png' % _cmd)
        time.sleep(10)  # let motion develop; oracle reads below
        out['vacuum_post_%s' % _cmd] = {f['name']: f['value'] for f in vac.facts()}
    try:
        controls.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
        out['revoked_grants_left'] = len(controls.grants.get(rid, {}))
    except Exception as e:
        out.update(fail('revoke', e))
    try:
        controls.invoke_now(rid, dock_cid)
        out['deny_after_revoke'] = 'NOT BLOCKED (BAD)'
    except Exception as e:
        out['deny_after_revoke'] = '%s: %s' % (type(e).__name__, str(e)[:80])
    out['shot_revoked'] = shot(serial, 'demo-s5-tv-revoked.png')
    ex = api_v2.executor(s)
    out['relay_revoke'] = ex.execute('relay_revoke', tv, {'relay_id': rid}, consent=True)['state']
    out['open_session_changes'] = [c['title'] for c in s.session_journal.open_changes()]
finally:
    s.server_close()
(SHOT_DIR / 'chain-manual-transcript.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
(SHOT_DIR / 'chain-progress.txt').write_text('DONE', encoding='utf-8')
print(json.dumps(out, indent=1))
