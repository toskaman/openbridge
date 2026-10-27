"""Owner-run: one redacted multi-device report on the real LAN. Writes artifacts/diagnostic-report.md; prints a summary."""
import json
from pathlib import Path
from src.runtime import api_v2
from src.server import create_server, start_windows_bridge
import os, time

s = create_server(0)
ex = api_v2.executor(s)
if os.environ.get('OPENBRIDGE_REPORT_WINDOWS'):
    s.windows_bridge = start_windows_bridge()
    for _ in range(40):
        if s.windows_bridge.connected(): break
        time.sleep(1)
ex.execute('bounded_discovery', 'fabric', {'providers': ['mdns', 'ssdp', 'android', 'freebox', 'windows']})
r = ex.execute('diagnostic_report', 'fabric', {})
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/diagnostic-report.md').write_text(r['result']['markdown'], encoding='utf-8')
print(json.dumps({'state': r['state'], 'summary': r['after'],
                  'sections': [(x['device'], x['state'], len(x['facts']), [w['name'] for w in x['warnings']]) for x in r['result']['report']['devices']]}))
s.server_close()
