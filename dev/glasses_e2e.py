"""End-to-end check of the glasses hub through OpenBridge itself, against HUD Studio (no glasses needed).

Needs: HUD Studio running (dev/launch_hud_studio.ps1 -Model "ENGO 3" -NoAdb) and `openbridge glasses run --link studio`.
Every step goes through the running hub's control port, exactly like a phone button, a gesture or a voice command;
a Studio screenshot is saved after each step.

    python dev/glasses_e2e.py --out E:/OpenBridgeAI/glasses_e2e [--tv-volume] [--voice]
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.hud_studio import send_control  # noqa: E402
from src.glasses.cli import send  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--tv-volume', action='store_true', help='press volume + then - on the real TV (net zero)')
    ap.add_argument('--voice', action='store_true', help='send a spoken-style command through the model')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    steps = []

    def shot(name):
        time.sleep(0.6)
        r = send_control({'cmd': 'screenshot', 'mode': 'lens'})
        src = r.get('path') or (r.get('paths') or [None])[0]
        if src and Path(src).exists():
            shutil.copy(src, out / ('%02d_%s.png' % (len(steps), name)))
        return src

    def step(name, req):
        r = send(req, timeout=60)
        steps.append({'step': name, 'request': req, 'reply': r, 'screenshot': shot(name)})
        print(json.dumps({'step': name, 'screen': r.get('screen'), 'last': (r.get('last') or {}).get('text') if isinstance(r.get('last'), dict) else None,
                          'voice': r.get('voice')}, ensure_ascii=False), flush=True)
        return r

    step('status', {'status': True})
    step('discord_toast', {'notify': {'package': 'com.discord', 'sender': 'Léa · #design', 'text': 'Les menus des lunettes sont superbes !'}})
    step('open_toast', {'press': 'ok'})
    step('back_home', {'press': 'home'})
    step('telegram', {'notify': {'package': 'org.telegram.messenger', 'sender': 'Maman', 'text': 'Tu passes dimanche ?'}})
    time.sleep(6.5)                                       # toast expires by itself
    step('sms', {'notify': {'package': 'com.google.android.apps.messaging', 'sender': '+33 6 12 34 56 78', 'text': 'Votre colis arrive demain.'}})
    time.sleep(6.5)
    step('inbox', {'press': 'ok'})
    step('inbox_next', {'press': 'next'})
    step('home', {'press': 'home'})
    step('to_tv', {'press': 'next'})
    step('tv', {'press': 'ok'})
    step('volume', {'press': 'ok'})
    if a.tv_volume:                                       # focus starts on "−": +1 then −1, net zero on the real TV
        step('focus_plus', {'press': 'next'})
        step('volume_up', {'press': 'ok'})
        step('focus_minus', {'press': 'prev'})
        step('volume_down', {'press': 'ok'})
    step('tv_back', {'press': 'back'})
    step('remote_focus', {'press': 'next'})
    step('remote_focus2', {'press': 'next'})
    step('remote', {'press': 'ok'})
    step('home2', {'press': 'home'})
    step('to_vacuum', {'press': 'next'})            # focus is still on TV: one wave reaches Vacuum
    step('vacuum', {'press': 'ok'})
    step('home3', {'press': 'home'})
    if a.voice:
        step('voice_unknown', {'voice': 'commande une pizza'})
        step('voice_tv', {'voice': 'monte le son de la télé'})
        step('voice_tv_down', {'voice': 'baisse le son de la télé'})
    step('final_status', {'status': True})
    (out / 'steps.json').write_text(json.dumps(steps, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


if __name__ == '__main__':
    main()
