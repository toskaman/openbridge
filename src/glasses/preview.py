"""Render glasses screens to PNG through the HUD Studio emulator (same parser and renderer as the Studio window).

    python -m src.glasses.preview --out captures/glasses       # every screen, pixel + lens views, and a contact sheet
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from src.glasses import ui
from src.glasses.notifications import Inbox

SAMPLE = [
    {'package': 'com.discord', 'sender': 'Léa · #design', 'text': 'Les nouveaux menus des lunettes sont superbes, on les montre demain ?'},
    {'package': 'org.telegram.messenger', 'sender': 'Maman', 'text': 'Tu passes dimanche ? Je fais une tarte aux pommes'},
    {'package': 'com.google.android.apps.messaging', 'sender': '+33 6 12 34 56 78', 'text': 'Votre colis arrive demain entre 9 h et 13 h.'},
    {'package': 'com.samsung.android.messaging', 'sender': 'Thomas', 'text': 'On se retrouve à 19 h devant le cinéma'},
]


def canvas(model='ENGO 3'):
    from src.adapters.activelook_emulator import HUDCanvas
    return HUDCanvas(model=model)


def to_image(frame: bytes, model='ENGO 3', mode='lens', scale=3):
    from src.adapters.hud_studio import render_hud
    c = canvas(model)
    c.dispatch(frame)
    if mode == 'raw':
        return c._img.copy()
    return render_hud(c._img, mode, scale, 13, mono='3' not in model)


def sample_context(now=None):
    now = now or time.time()
    inbox = Inbox(clock=lambda: now)
    for i, n in enumerate(SAMPLE):
        inbox.add(dict(n, time=now - [40, 600, 3000, 7200][i]))
    ctx = ui.Context(inbox=inbox, clock=lambda: now, phone_battery=84, glasses_battery=76, linked=True,
                     tv_name='Living room TV', tv_app='YouTube', tv_volume=32, vacuum_state='docked', vacuum_battery=92)
    return ctx


def gallery(now=None):
    """(name, frame bytes) for every screen worth showing."""
    ctx = sample_context(now)
    m = ui.Menu(ctx)
    out = []

    def shot(name):
        out.append((name, m.render().to_bytes()))

    for i, name in enumerate(('home_messages', 'home_tv', 'home_vacuum', 'home_voice', 'home_settings')):
        m.stack[0].focus = i
        shot(name)
    m.stack[0].focus = 0
    m.handle('ok'); shot('inbox')
    m.handle('next'); shot('inbox_focus2')
    m.handle('ok'); shot('message')
    del m.stack[1:]
    m.stack[0].focus = 1
    m.handle('ok'); shot('tv')
    for screen, name, focus in ((ui.VolumeScreen(), 'tv_volume', 1), (ui.AppsScreen(), 'tv_apps', 0),
                                (ui.RemoteScreen(), 'tv_remote', 4), (ui.PowerScreen(), 'tv_power', 0)):
        screen.focus = focus
        m.stack.append(screen); shot(name); m.stack.pop()
    ctx.banner = {'ok': True, 'text': 'Volume up ✓', 'until': ctx.clock() + 5}
    v = ui.VolumeScreen(); v.focus = 1
    m.stack.append(v); shot('tv_volume_done'); m.stack.pop()
    ctx.banner = None
    del m.stack[1:]
    m.stack.append(ui.VacuumScreen()); shot('vacuum')
    ctx.banner = {'ok': True, 'text': 'Start cleaning ✓', 'until': ctx.clock() + 5}
    shot('vacuum_started'); ctx.banner = None
    del m.stack[1:]
    for st, text, res in (('idle', '', ''), ('listening', '', ''), ('thinking', 'baisse le son de la télé', ''),
                          ('done', 'baisse le son de la télé', 'Volume down ✓'),
                          ('failed', 'commande une pizza', 'Not something the glasses can do')):
        ctx.voice = {'state': st, 'text': text, 'result': res}
        m.stack[1:] = [ui.VoiceScreen()]
        shot('voice_' + st)
    del m.stack[1:]
    m.stack.append(ui.SettingsScreen()); shot('settings')
    m.stack[1:] = [ui.Calibration()]; shot('calibration')
    del m.stack[1:]
    m.stack[0].focus = 1
    ctx.toast = dict(ctx.inbox.list()[0], until=ctx.clock() + 5)
    shot('toast_over_home')
    ctx.toast = None
    return out


def write_gallery(out_dir, model='ENGO 3', modes=('lens', 'raw')):
    from PIL import Image
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shots = gallery()
    tiles = []
    for name, frame in shots:
        for mode in modes:
            img = to_image(frame, model, mode)
            img.save(out / ('%s_%s.png' % (name, mode)))
            if mode == modes[0]:
                tiles.append(img)
    w, h = tiles[0].size
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * w // 2, rows * h // 2), (8, 10, 14))
    for i, t in enumerate(tiles):
        sheet.paste(t.resize((w // 2, h // 2)), ((i % cols) * w // 2, (i // cols) * h // 2))
    sheet.save(out / 'contact_sheet.png')
    return [n for n, _ in shots]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='captures/glasses')
    ap.add_argument('--model', default='ENGO 3')
    a = ap.parse_args(argv)
    names = write_gallery(a.out, a.model)
    print('%d screens -> %s' % (len(names), a.out))


if __name__ == '__main__':
    main()
