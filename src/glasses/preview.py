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


def sample_route():
    """A 2.4 km loop with left and right turns (synthetic, for previews and tests)."""
    from src.glasses.nav import Route
    lat0, lon0 = 48.8566, 2.3522
    m_lat, m_lon = 1 / 111320.0, 1 / (111320.0 * 0.6587)
    legs = [(0, 400), (300, 0), (0, -200), (250, 0), (0, 500), (-550, 0), (0, -700)]
    pts, y, x = [(lat0, lon0)], 0.0, 0.0
    for dy, dx in legs:
        steps = max(1, int(max(abs(dy), abs(dx)) // 20))
        for k in range(1, steps + 1):
            pts.append((lat0 + (y + dy * k / steps) * m_lat, lon0 + (x + dx * k / steps) * m_lon))
        y, x = y + dy, x + dx
    return Route('Boucle du canal', pts, [{'name': 'Fontaine', 'lat': lat0 + 300 * m_lat, 'lon': lon0 + 420 * m_lon, 'kind': 'water'}])


def sport_context(ctx, until_m=900, ghost_faster=False, workout=True):
    """Run a simulated session along the sample route up to `until_m` and put its snapshot in ctx.sport."""
    from src.glasses import sport as S
    from src.glasses.live import SportEngine
    from src.glasses.metrics import Observation
    from src.glasses.nav import simulate
    route = sample_route()
    now = ctx.clock()
    eng = SportEngine('run', clock=lambda: now, max_hr=190, lang=ctx.lang)
    eng.set_route(route)
    eng.set_ghost(S.Ghost([(t, t * (3.4 if ghost_faster else 3.1)) for t in range(0, 900, 10)], 'Record 10 km'))
    if workout:
        eng.set_workout(S.Workout.intervals('6 x 400 m', 300, 6, 400, 90, 300, target_pace=255))
    start = now - until_m / 3.3
    for pt in simulate(route, 3.3, start, 1.0):
        if pt.t > now:
            break
        eng.gps(pt)
    eng.observe(Observation('heart_rate_bpm', 162, 'hrm', 'ble_heart_rate', now))
    eng.observe(Observation('cadence_spm', 172, 'pod', 'ble_rsc', now))
    ctx.sport = eng.snapshot()
    return eng


def gallery(now=None, lang='en'):
    """(name, frame bytes) for every screen worth showing."""
    ctx = sample_context(now)
    ctx.lang = lang
    m = ui.Menu(ctx)
    out = []
    sfx = '' if lang == 'en' else '_' + lang

    def shot(name):
        out.append((name + sfx, m.render().to_bytes()))

    for i, name in enumerate(('home_messages', 'home_sport', 'home_tv', 'home_vacuum', 'home_voice', 'home_settings')):
        m.stack[0].focus = i
        shot(name)
    m.stack[0].focus = 0
    m.handle('ok'); shot('inbox')
    m.handle('next'); shot('inbox_focus2')
    m.handle('ok'); shot('message')
    del m.stack[1:]
    eng = sport_context(ctx)
    m.stack.append(ui.SportMenu()); shot('sport_menu')
    for screen, name in ((ui.SportDashboard('run'), 'sport_run'), (ui.SportDashboard('ride'), 'sport_ride'),
                         (ui.NavScreen(), 'sport_nav'), (ui.GhostScreen(), 'sport_ghost'),
                         (ui.WorkoutScreen(), 'sport_workout')):
        m.stack[1:] = [screen]
        shot(name)
    from src.glasses.events import HudEvent
    from src.glasses.i18n import t as _t
    ctx.event = HudEvent('nav.turn', 'hud.navigation.next_turn', 'INTERACTION',
                         {'direction': _t('hud.dir.left', lang), 'distance': '50 m'}, created_at=ctx.clock())
    m.stack[1:] = [ui.SportDashboard('run')]; shot('sport_turn_alert')
    ctx.event = None
    off = dict(ctx.sport['nav'], off_route=True, off_by_m=63)
    ctx.sport = dict(ctx.sport, nav=off)
    m.stack[1:] = [ui.NavScreen()]; shot('sport_off_route')
    ctx.sport = {}
    if lang != 'en':
        del m.stack[1:]
        m.stack.append(ui.SettingsScreen()); shot('settings')
        return out
    del m.stack[1:]
    m.stack[0].focus = 2
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
    m.stack[0].focus = 2
    ctx.toast = dict(ctx.inbox.list()[0], until=ctx.clock() + 5)
    shot('toast_over_home')
    ctx.toast = None
    return out


def write_gallery(out_dir, model='ENGO 3', modes=('lens', 'raw')):
    from PIL import Image
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shots = gallery() + gallery(lang='fr')
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
