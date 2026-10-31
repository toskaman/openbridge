"""S5b safe acceptance: T2 panel (TV volume + vacuum find-me) -> TV install ->
hold-press SEEK (no motion) -> Tuya poll oracle -> revoke -> deny.

Same product paths as dev/s5_tv_panel_chain.py, but the pressed button is
`vacuum_command seek` (audible beep, zero motion) instead of dock, and the
vacuum is polled every 2 s x 15 to catch any state transit as a machine
oracle. Prints sanitized JSON only (no keys, no codes).

Usage: python -m dev.s5b_safe_seek_chain [PATCH] [VACUUM_LABEL]
Default PATCH: artifacts/s5-tv-panel-31oct/t2-propose-medium.json
"""
import json
import re
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

PATCH = sys.argv[1] if len(sys.argv) > 1 else 'artifacts/s5-tv-panel-31oct/t2-propose-medium.json'
VACUUM_LABEL = sys.argv[2] if len(sys.argv) > 2 else 'Robot vacuum (Tuya)'
SHOT_DIR = Path('E:/shots/s5b')
SHOT_DIR.mkdir(parents=True, exist_ok=True)

from src.server import create_server  # noqa: E402
from src.runtime import api_v2  # noqa: E402
from src.cli import ensure_discovery, default_providers  # noqa: E402

out = {}


def fail(step, error):
    out[step] = 'FAILED: %s: %s' % (type(error).__name__, str(error)[:160])
    return out


def shot(serial, name):
    dest = SHOT_DIR / name
    subprocess.run(['adb', '-s', serial, 'shell', 'screencap', '-p', '/sdcard/s5bshot.png'],
                   capture_output=True, timeout=60)
    p = subprocess.run(['adb', '-s', serial, 'pull', '/sdcard/s5bshot.png', str(dest)],
                       capture_output=True, timeout=60)
    subprocess.run(['adb', '-s', serial, 'shell', 'rm', '/sdcard/s5bshot.png'],
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
    try:
        return _ocr_run(png_path).text
    except Exception as e:
        return 'OCR_ERROR:%s: %s' % (type(e).__name__, str(e)[:100])


def ocr_words(png_path):
    words = []
    for line in _ocr_run(png_path).lines:
        for w in line.words:
            r = w.bounding_rect
            words.append((w.text, int(r.x), int(r.y), int(r.width), int(r.height)))
    return words


def find_button_center(png_path, label_words):
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
    from PIL import Image, ImageOps
    im = Image.open(png_path).convert('L')
    w, h = im.size
    im = im.resize((w * 2, h * 2))
    im = ImageOps.autocontrast(im, cutoff=1)
    im = im.point(lambda v: 255 if v > 150 else 0)
    outp = str(png_path) + '.big.png'
    im.save(outp)
    return outp


def code_candidates(text):
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
    found, seen = [], set()
    for i in range(rounds):
        if i:
            time.sleep(3)
        png = shot(serial, 's5b_code_%d.png' % i)
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
    tv = next(k for k, d in s.fabric_registry.devices.items()
              if d['category'] == 'tv' and any(i.strong for i in d['identifiers']))
    handle = next(iter(s.fabric_registry.devices[tv]['handles'].values()))
    serial = next(k for k, v in s.android._handles.items() if v == handle)
    out['tv_serial_suffix'] = serial[-9:]
    adb = lambda *a: subprocess.run(['adb', '-s', serial, *a], capture_output=True,
                                    text=True, encoding='utf-8', timeout=60).stdout
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
    # Confirm round by round: the code TTL is 120 s and OCR is slow; reading
    # all rounds first lets the code expire while its pixels stay on screen.
    from src.fabric import relay as fabric_relay
    conf, used, seen, tried = None, None, set(), []
    for i in range(4):
        if i:
            time.sleep(2)
        png = shot(serial, 's5b_code_%d.png' % i)
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
                if code in seen or len(tried) >= 4:
                    continue
                seen.add(code)
                tried.append((code, '%s/r%d' % (rule, i)))
                try:
                    conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
                    used = '%s/r%d' % (rule, i)
                    break
                except fabric_relay.RelayError as e:
                    out['confirm_%s_r%d' % (rule, i)] = str(e)[:80]
            if conf is not None:
                break
        if conf is not None:
            break
    out['code_candidates'] = tried
    out['code_read_from_screen'] = bool(tried)
    if conf is None:
        out.update(fail('pair_confirm', RuntimeError('no candidate accepted')))
        raise SystemExit(json.dumps(out, indent=1))
    out['code_match_rule'] = used
    out['paired'] = conf['state']
    out['declared_caps'] = sorted((conf.get('declared') or {}).get('capabilities', ()))
    relay = s.relays.relays[rid]
    status = fabric_relay.verify(
        relay['key'], relay['send'](relay, fabric_relay.command(relay['key'], rid, 'get_status')),
        relay['seen']).get('params', {})
    out['full_control'] = bool(fabric_relay.reported_full_control(status))
    from src.forge import v4_ui
    from src.runtime import dashboards as D
    doc = json.loads(Path(PATCH).read_text(encoding='utf-8'))
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
        D.install_patch(controls, rid, patch, VACUUM_LABEL,
                        D.BINDABLE_PATCH_SKILLS, consent=True,
                        resolve_target=router.resolve_target)
    except Exception as e:
        out.update(fail('install', e))
        raise SystemExit(json.dumps(out, indent=1))
    grants = dict(controls.grants.get(rid, {}))
    out['installed'] = sorted((c['label'], c['skill_id'], c['params']) for c in grants.values())
    seek_cid = next(cid for cid, c in grants.items() if c['params'].get('command') == 'seek')
    out['shot_installed'] = shot(serial, 's5b_installed.png')
    out['press_mode'] = 'hold'
    try:
        center = find_button_center(out['shot_installed'], ('find', 'vacuum'))
        out['hold_xy'] = center
        if center is None:
            raise RuntimeError('find-vacuum button not located via OCR')
        x, y = center
        adb('shell', 'input', 'touchscreen', 'swipe', str(x), str(y), str(x), str(y), '1500')
        time.sleep(8)
        hits = [h for h in controls.history if h.get('control_id') == seek_cid]
        out['press_history'] = json.dumps(hits[-1], default=str)[:1500] if hits else 'NO_HISTORY_ENTRY'
        out['shot_pressed'] = shot(serial, 's5b_pressed.png')
    except Exception as e:
        out.update(fail('press_hold', e))
    # Machine oracle: poll Tuya for any state transit after the beep command.
    polls = []
    for _ in range(15):
        try:
            polls.append({f['name']: f['value'] for f in vac.facts()
                          if f['name'] in ('vacuum_status', 'fault_code', 'work_mode')})
        except Exception as e:
            polls.append({'poll_error': type(e).__name__})
        time.sleep(2)
    out['vacuum_polls'] = polls
    out['vacuum_post'] = {f['name']: f['value'] for f in vac.facts()}
    try:
        controls.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
        out['revoked_grants_left'] = len(controls.grants.get(rid, {}))
    except Exception as e:
        out.update(fail('revoke', e))
    try:
        controls.invoke_now(rid, seek_cid)
        out['deny_after_revoke'] = 'NOT BLOCKED (BAD)'
    except Exception as e:
        out['deny_after_revoke'] = '%s: %s' % (type(e).__name__, str(e)[:80])
    out['shot_revoked'] = shot(serial, 's5b_revoked.png')
    ex = api_v2.executor(s)
    out['relay_revoke'] = ex.execute('relay_revoke', tv, {'relay_id': rid}, consent=True)['state']
    out['open_session_changes'] = [c['title'] for c in s.session_journal.open_changes()]
finally:
    s.server_close()
print(json.dumps(out, indent=1))
