"""End-to-end battery through OpenBridge itself: spoken requests (US English, UK English, French) go through
`openbridge ha say` (our model -> router gate -> typed primitive -> Home Assistant -> read-back), then a link
created by voice is approved and fired for real. Writes one JSON report.

    python dev/ai_training/home_battery.py --out E:/OpenBridgeAI/runs/v3/battery.json
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (dialect, request, expected skill or 'unsupported' / 'clarify', must act on HA)
BATTERY = [
    ('en-US', 'turn on the kitchen lights', 'home.turn_on', True),
    ('en-US', 'switch off the ceiling lights', 'home.turn_off', True),
    ('en-US', 'dim the office lights to 30%', 'home.set_brightness', True),
    ('en-US', 'set the bed light to 70 percent', 'home.set_brightness', True),
    ('en-US', 'set the thermostat to 21 degrees', 'home.set_temperature', True),
    ('en-US', 'pause the music in the kitchen', 'home.media_pause', True),
    ('en-US', 'resume the living room speaker', 'home.media_play', True),
    ('en-US', 'set the bedroom speaker volume to 25', 'home.media_volume', True),
    ('en-US', 'close the kitchen blinds', 'home.cover_close', True),
    ('en-US', 'open the living room blinds', 'home.cover_open', True),
    ('en-US', 'lock the front door', 'home.lock', True),
    ('en-US', 'turn on the ceiling fan', 'home.turn_on', True),
    ('en-US', 'turn off all the lights', 'home.turn_off', True),
    ('en-US', 'unlock the front door', 'unsupported', False),
    ('en-US', 'open the garage', 'unsupported', False),
    ('en-US', 'turn it on', 'clarify', False),
    ('en-US', 'what could my devices do together?', 'create.suggest', False),
    ('en-US', 'which of my devices are reliable?', 'learn.report', False),
    ('en-US', 'start the vacuum', 'vacuum.start', False),
    ('en-US', 'stop the kitchen blinds', 'home.cover_stop', True),
    ('en-US', 'run the robot vacuum', 'home.vacuum_start', True),
    ('en-US', 'pause the robot vacuum', 'home.vacuum_pause', True),
    ('en-US', 'set the kitchen light to 3000 kelvin', 'home.set_color_temp', True),
    ('en-US', 'make the bed light blue', 'home.set_color', True),
    ('en-US', 'set the living room fan to 60', 'home.fan_speed', True),
    ('en-US', 'skip this song', 'home.media_next', True),
    ('en-US', 'go back one track', 'home.media_previous', True),
    ('en-US', 'mute the bedroom speaker', 'home.media_mute', True),
    ('en-US', 'set the thermostat to heat mode', 'home.set_mode', True),
    ('en-US', 'send the robot vacuum back to its dock', 'home.vacuum_dock', True),
    ('en-US', 'order me a pizza', 'unsupported', False),
    ('en-GB', 'switch the big light off', 'home.turn_off', True),
    ('en-GB', 'put the heating on 20', 'home.set_temperature', True),
    ('en-GB', 'draw the curtains in the lounge', 'home.cover_close', True),
    ('en-GB', 'lock the kitchen door, ta', 'home.lock', True),
    ('en-GB', 'turn the bedroom music down to 15', 'home.media_volume', True),
    ('en-GB', 'pop the living room fan on', 'home.turn_on', True),
    ('en-GB', 'switch every light on', 'home.turn_on', True),
    ('en-GB', 'stop the lounge blinds, ta', 'home.cover_stop', True),
    ('en-GB', 'set the cleaning robot off', 'home.vacuum_start', True),
    ('en-GB', 'put the big light on 4000 kelvin', 'home.set_color_temp', True),
    ('en-GB', 'back one track on the lounge sonos', 'home.media_previous', True),
    ('en-GB', 'switch the burglar alarm off', 'unsupported', False),
    ('en-GB', 'turn the telly down', 'tv_volume_step', False),
    ('en-GB', 'any clever ideas for my gadgets?', 'create.suggest', False),
    ('fr', 'allume la lumière de la cuisine', 'home.turn_on', True),
    ('fr', 'éteins le plafonnier', 'home.turn_off', True),
    ('fr', 'mets la lampe du bureau à 40 %', 'home.set_brightness', True),
    ('fr', 'règle le chauffage sur 19 degrés', 'home.set_temperature', True),
    ('fr', 'mets la musique de la chambre en pause', 'home.media_pause', True),
    ('fr', 'ferme les stores de la cuisine', 'home.cover_close', True),
    ('fr', 'ouvre les volets du salon', 'home.cover_open', True),
    ('fr', "verrouille la porte d'entrée", 'home.lock', True),
    ('fr', 'allume le ventilateur du salon', 'home.turn_on', True),
    ('fr', 'éteins toutes les lumières', 'home.turn_off', True),
    ('fr', 'déverrouille la porte', 'unsupported', False),
    ('fr', 'ouvre le garage', 'unsupported', False),
    ('fr', 'allume', 'clarify', False),
    ('fr', "propose-moi des idées d'automatisations", 'create.suggest', False),
    ('fr', 'quels appareils sont fiables ?', 'learn.report', False),
    ('fr', 'commande une pizza', 'unsupported', False),
    ('fr', 'démarre l aspirateur', 'vacuum.start', False),
    ('fr', 'lance le robot aspirateur', 'home.vacuum_start', True),
    ('fr', 'mets le robot aspirateur en pause', 'home.vacuum_pause', True),
    ('fr', 'stoppe les stores de la cuisine', 'home.cover_stop', True),
    ('fr', 'renvoie le robot aspirateur à sa base', 'home.vacuum_dock', True),
    ('fr', 'mets la lampe à 2700 kelvins', 'home.set_color_temp', True),
    ('fr', 'mets le salon en rouge', 'home.set_color', True),
    ('fr', 'mets le ventilateur à 70', 'home.fan_speed', True),
    ('fr', 'chanson suivante', 'home.media_next', True),
    ('fr', 'mets le chauffage en mode froid', 'home.set_mode', True),
]
LINK_REQUESTS = [
    ('en-US', 'when the living room TV starts playing, dim the kitchen lights to 20%'),
    ('fr', "quand la musique du salon se met en pause, allume le plafonnier"),
    ('en-GB', 'whenever the front door locks, switch the kitchen lights off'),
]


def cli(*argv, timeout=300):
    r = subprocess.run([sys.executable, '-m', 'src.cli', *argv, '--json'], cwd=ROOT, capture_output=True, text=True,
                       encoding='utf-8', timeout=timeout)
    t = r.stdout
    try:
        return json.loads(t[t.index('{'):])
    except ValueError:
        return {'ok': False, 'error': {'raw': (t + r.stderr)[-400:]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--intent-model', default='openbridge-intent')
    ap.add_argument('--endpoint', default='http://127.0.0.1:11434')
    a = ap.parse_args()
    rows = []
    for dialect, text, want, acts in BATTERY:
        res = cli('ha', 'say', text, '--intent-model', a.intent_model, '--endpoint', a.endpoint, '--consent', 'ALLOW')
        d = res.get('data') or {}
        it = d.get('intent') or {}
        got = it.get('skill_id') or {'needs_clarification': 'clarify', 'unsupported': 'unsupported'}.get(it.get('status'), it.get('status'))
        rows.append({'dialect': dialect, 'text': text, 'want': want, 'got': got, 'understood': got == want,
                     'acted': bool(d.get('done')) if acts else None, 'entities': (d.get('plan') or {}).get('entities'),
                     'receipts': d.get('receipts'), 'note': d.get('note'), 'latency_s': d.get('understood_in_s'),
                     'error': res.get('error')})
        print(json.dumps({k: rows[-1][k] for k in ('dialect', 'text', 'got', 'understood', 'acted', 'entities')}, ensure_ascii=False), flush=True)
    links = []
    for dialect, text in LINK_REQUESTS:
        res = cli('ha', 'say', text, '--intent-model', a.intent_model, '--endpoint', a.endpoint)
        d = res.get('data') or {}
        links.append({'dialect': dialect, 'text': text, 'intent': d.get('intent'), 'result': d.get('result'), 'note': d.get('note')})
        print(json.dumps(links[-1], ensure_ascii=False), flush=True)
    fired = None
    first = next((l for l in links if (l.get('result') or {}).get('link')), None)
    if first:
        lid = first['result']['link']
        cli('links', 'approve', lid, '--consent', 'ALLOW')
        trig, state = first['result']['when'], first['result']['state']
        prep = {'playing': 'pause', 'paused': 'play', 'locked': None}.get(state)
        if prep:
            cli('ha', 'do', trig, prep, '--consent', 'ALLOW')
        watch = subprocess.Popen([sys.executable, '-m', 'src.cli', 'links', 'watch', '--seconds', '30', '--interval', '2', '--json'],
                                 cwd=ROOT, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        time.sleep(9)
        cause = {'playing': 'play', 'paused': 'pause', 'locked': 'lock'}.get(state)
        caused = cli('ha', 'do', trig, cause, '--consent', 'ALLOW') if cause else None
        out_ = watch.communicate(timeout=120)[0]
        try:
            fired = json.loads(out_[out_.index('{'):]).get('data')
        except ValueError:
            fired = {'raw': out_[-400:]}
        fired = {'link': lid, 'trigger': trig, 'state': state, 'caused': (caused or {}).get('data', {}).get('state'), 'watch': fired}
    for l in links:
        if (l.get('result') or {}).get('link'):
            cli('links', 'remove', l['result']['link'])
    n = len(rows)
    acts = [r for r in rows if r['acted'] is not None]
    summary = {'requests': n, 'understood_pct': round(100 * sum(r['understood'] for r in rows) / n, 1),
               'acted_verified_pct': round(100 * sum(1 for r in acts if r['acted']) / max(1, len(acts)), 1),
               'by_dialect': {d: round(100 * sum(r['understood'] for r in rows if r['dialect'] == d) /
                                       max(1, sum(1 for r in rows if r['dialect'] == d)), 1) for d in ('en-US', 'en-GB', 'fr')},
               'links_created_by_voice': sum(1 for l in links if (l.get('result') or {}).get('link')),
               'link_fired': bool(fired and (fired.get('watch') or {}).get('by_result', {}).get('VERIFIED')),
               'latency_p50_s': sorted(r['latency_s'] or 0 for r in rows)[n // 2]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({'summary': summary, 'rows': rows, 'links': links, 'fired': fired}, ensure_ascii=False, indent=1),
                           encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
