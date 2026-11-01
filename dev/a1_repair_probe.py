"""A1 emulator validation: a fresh (re-)pairing must reset full_control.

Scenario (official Android emulator, black-box + white-box reads):
  pair#1 -> full_control False -> UI-grant Allow -> True -> force-stop
  (kill WITHOUT unpair, the A1 hole) -> re-pair#2 -> MUST be False again
  (the fix) -> white-box pref read -> UI re-allow -> True -> bounded
  Doze check -> UI unpair -> pairing gone.
Writes E:/shots/a1-emu/a1-transcript.json. No retries on product assertions.
Usage: python -m dev.a1_repair_probe [serial]  (default emulator-5556)
"""
import json
import re
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path
from xml.etree import ElementTree as ET

SERIAL = sys.argv[1] if len(sys.argv) > 1 else 'emulator-5556'
OUT = Path('E:/shots/a1-emu')
OUT.mkdir(parents=True, exist_ok=True)

from src.server import create_server  # noqa: E402
from src.cli import ensure_discovery, default_providers  # noqa: E402
from src.fabric import relay as fabric_relay  # noqa: E402

out = {'serial': SERIAL, 'steps': [], 'fail_stage': None}


def step(name, ok, detail=''):
    out['steps'].append({'step': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print('STEP %s: %s %s' % (name, 'OK' if ok else 'FAIL', str(detail)[:200]), flush=True)
    return bool(ok)


def die(stage, detail):
    out['fail_stage'] = stage
    step(stage, False, detail)
    (OUT / 'a1-transcript.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    raise SystemExit('A1 FAIL at %s: %s' % (stage, detail))


def adb(*a, timeout=60):
    r = subprocess.run(['adb', '-s', SERIAL, *a], capture_output=True,
                       text=True, encoding='utf-8', timeout=timeout)
    return r.stdout


def ui_dump(name='a1-ui.xml'):
    adb('shell', 'uiautomator', 'dump', '/sdcard/a1-ui.xml')
    subprocess.run(['adb', '-s', SERIAL, 'pull', '/sdcard/a1-ui.xml', str(OUT / name)],
                   capture_output=True, timeout=60)
    return ET.parse(str(OUT / name)).getroot()


def ui_nodes_with(root, *needles):
    hits = []
    for n in root.iter('node'):
        t = (n.get('text') or '') + ' ' + (n.get('content-desc') or '')
        if all(x.lower() in t.lower() for x in needles):
            hits.append(n)
    return hits


def tap(node):
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds') or '')
    if not m:
        raise RuntimeError('node has no bounds')
    x1, y1, x2, y2 = map(int, m.groups())
    adb('shell', 'input', 'tap', str((x1 + x2) // 2), str((y1 + y2) // 2))


def pair_code_candidates(root):
    texts = []
    for n in root.iter('node'):
        for k in ('text', 'content-desc'):
            v = n.get(k) or ''
            if re.search(r'\d', v):
                texts.append(v)
    joined = ' | '.join(texts)
    cands = []
    for m in re.finditer(r'(\d{3})\s*(\d{3})', joined):
        c = m.group(1) + m.group(2)
        if c not in cands:
            cands.append(c)
    for m in re.finditer(r'(?<!\d)(\d{6})(?!\d)', joined):
        if m.group(1) not in cands:
            cands.append(m.group(1))
    return cands, joined[:500]


def main():
    s = create_server(0)
    ensure_discovery(s, default_providers(Namespace(providers=None)))
    match = [(k, v) for k, v in s.android._handles.items() if k == SERIAL or k.endswith(SERIAL)]
    if not match:
        die('discovery', 'serial %s not in android handles %s' % (SERIAL, sorted(s.android._handles)))
    handle = match[0][1]
    step('discovery', True, 'handle for %s' % SERIAL)

    def do_pair(tag):
        adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
        time.sleep(3)
        pair = s.relay_action('/api/relay-pair-start', {'device_id': handle})
        rid = pair['relay_id']
        conf, cands = None, []
        try:
            cands, seen = pair_code_candidates(ui_dump('%s-ui.xml' % tag))
            (OUT / ('%s-cands.txt' % tag)).write_text('\n'.join(cands) + '\n---\n' + seen, encoding='utf-8')
        except Exception as e:
            out[tag + '-uiauto'] = 'dump failed: %s' % str(e)[:120]
        for code in cands[:3]:
            try:
                conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
                out[tag + '-code-source'] = 'uiautomator'
                break
            except fabric_relay.RelayError as e:
                out['%s-confirm-%s' % (tag, code)] = str(e)[:80]
        if conf is None:  # operator-assist fallback (emulator test only)
            adb('shell', 'screencap', '-p', '/sdcard/a1-pair.png')
            subprocess.run(['adb', '-s', SERIAL, 'pull', '/sdcard/a1-pair.png',
                            str(OUT / ('%s-pair.png' % tag))], capture_output=True, timeout=60)
            (OUT / 'a1-progress.txt').write_text('NEED_CODE_' + tag, encoding='utf-8')
            (OUT / 'a1-code.txt').unlink(missing_ok=True)
            deadline = time.monotonic() + 100  # inside the 120 s TV/phone TTL
            while time.monotonic() < deadline:
                p = OUT / 'a1-code.txt'
                if p.exists():
                    t = p.read_text(encoding='utf-8').strip().replace(' ', '')
                    if re.fullmatch(r'\d{6}', t):
                        try:
                            conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': t})
                            out[tag + '-code-source'] = 'operator-assist'
                        except fabric_relay.RelayError as e:
                            out[tag + '-assist-err'] = str(e)[:80]
                        break
                time.sleep(3)
        if conf is None:
            die(tag, 'no pairing code accepted (uiautomator + assist exhausted)')
        step(tag, True, 'paired %s via %s' % (rid, out.get(tag + '-code-source')))
        return rid

    def full_control(rid):
        relay = s.relays.relays[rid]
        st = fabric_relay.verify(
            relay['key'], relay['send'](relay, fabric_relay.command(relay['key'], rid, 'get_status')),
            relay['seen']).get('params', {})
        return bool(fabric_relay.reported_full_control(st))

    def grant_ui(tag):
        root = ui_dump('%s-grant-ui.xml' % tag)
        toggles = ui_nodes_with(root, 'Full control')
        if not toggles:
            return False, 'no Full control node on screen'
        tap(toggles[0])
        time.sleep(2)
        allows = ui_nodes_with(ui_dump('%s-allow-ui.xml' % tag), 'Allow')
        if not allows:
            return False, 'no Allow dialog after toggle tap'
        tap(allows[0])
        time.sleep(2)
        return True, 'tapped Full control + Allow'

    # 1. fresh install: pair, expect full_control False.
    rid1 = do_pair('pair1')
    if full_control(rid1):
        die('fresh-false', 'fresh pairing already reports full control')
    step('fresh-false', True, 'fresh pairing reports no full control')

    # 2. UI grant -> True.
    ok, msg = grant_ui('grant1')
    if not ok or not full_control(rid1):
        die('grant-true', 'UI grant failed: %s (status=%s)' % (msg, full_control(rid1)))
    step('grant-true', True, msg)

    # 3. force-stop WITHOUT unpair (the A1 hole), relaunch, re-pair.
    adb('shell', 'am', 'force-stop', 'fr.openbridge.companion')
    time.sleep(2)
    rid2 = do_pair('pair2')
    if full_control(rid2):
        die('repair-false', 'STALE full_control survived re-pair (A1 bug present)')
    step('repair-false', True, 're-pair reports no full control (A1 fixed)')

    # 4. white-box: pref must be false on disk (root, emulator only).
    try:
        prefs = adb('shell', 'su', '0', 'cat', '/data/data/fr.openbridge.companion/shared_prefs/*.xml')
        out['prefs_snippet'] = prefs[:400]
        m = re.search(r'full_control[^>]*value="(\w+)"', prefs) or re.search(r'<boolean name="full_control" value="(\w+)"', prefs)
        if not m or m.group(1) != 'false':
            die('prefs-false', 'on-disk full_control pref is not false: %s' % prefs[:200])
        step('prefs-false', True, 'on-disk pref false')
    except SystemExit:
        raise
    except Exception as e:
        die('prefs-false', 'white-box read failed: %s' % str(e)[:150])

    # 5. re-allow via UI -> True again (consent path intact).
    ok, msg = grant_ui('grant2')
    if not ok or not full_control(rid2):
        die('reallow-true', 'UI re-allow failed: %s' % msg)
    step('reallow-true', True, msg)

    # 6. bounded Doze check: force-idle, relay must still answer.
    try:
        adb('shell', 'dumpsys', 'deviceidle', 'force-idle')
        time.sleep(3)
        alive = full_control(rid2)  # any signed reply proves liveness
        adb('shell', 'dumpsys', 'deviceidle', 'unforce')
        step('doze-alive', True, 'signed get_status answered under force-idle (full_control=%s)' % alive)
    except Exception as e:
        try:
            adb('shell', 'dumpsys', 'deviceidle', 'unforce')
        except Exception:
            pass
        die('doze-alive', 'relay silent under force-idle: %s' % str(e)[:150])

    # 7. UI unpair -> pairing gone (signed call must fail).
    root = ui_dump('unpair-ui.xml')
    ups = ui_nodes_with(root, 'npair')
    if ups:
        tap(ups[0])
        time.sleep(2)
    try:
        full_control(rid2)
        die('unpair-gone', 'relay still answers after UI unpair')
    except (fabric_relay.RelayError, OSError, KeyError, ValueError):
        step('unpair-gone', True, 'relay silent after UI unpair')
    (OUT / 'a1-transcript.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    (OUT / 'a1-progress.txt').write_text('DONE', encoding='utf-8')
    print('A1 VERDICT: PASS', flush=True)


if __name__ == '__main__':
    main()
