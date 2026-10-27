"""OpenBridge Companion portal: a LAN onboarding page so any PC (or the jury) can download the agent and
start it in one copy-paste, with a live status that flips to Connected when the PC links back.

Read-only and self-contained. It serves exactly one binary (the path given on the command line), proxies the
local BridgeWindows daemon (127.0.0.1:9877) for live connection state and the launch command, accepts only
private-network clients, and stops itself after --minutes. It never generates or stores keys.

Usage: python -m dev.agent_portal <lan-ip> <port> <path-to-agent.exe> [--minutes 45]
"""
import hashlib
import html
import ipaddress
import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DAEMON = 'http://127.0.0.1:9877'


def daemon_state():
    """Live state from the BridgeWindows daemon: connected?, agent version/arch, launch command, LAN IPs."""
    out = {'connected': False, 'version': None, 'arch': None, 'command': None, 'lan_ips': [], 'metrics': None}
    try:
        with urllib.request.urlopen(DAEMON + '/health', timeout=2) as r:
            h = json.loads(r.read())
        out['connected'] = bool(h.get('connected'))
        info = h.get('agent_info') or {}
        out['version'], out['arch'] = info.get('version'), info.get('arch')
    except Exception:
        return out
    if out['connected']:
        try:
            body = json.dumps({'tool': 'remote_telemetry', 'args': {}}).encode()
            req = urllib.request.Request(DAEMON + '/tool', body, {'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=3) as r:
                inner = json.loads(r.read()).get('result', '{}')
            t = json.loads(inner) if isinstance(inner, str) else inner
            disks = t.get('disks') or []
            free_gb = round(sum(d.get('free_bytes', 0) for d in disks) / 1024 ** 3, 1) if disks else None
            out['metrics'] = {'cpu': t.get('cpu_load_percent'), 'ram_used_pct': t.get('ram_used_percent'),
                              'ram_avail_mb': t.get('ram_avail_mb'), 'cores': t.get('cpu_cores'),
                              'disk_free_gb': free_gb, 'uptime_h': round(t.get('uptime_seconds', 0) / 3600, 1),
                              'rtt_ms': t.get('round_trip_ms')}   # hostname and identifiers are intentionally omitted
        except Exception:
            pass
    # remote_network_helper always returns the full copy-paste launch command (with host/port/token),
    # whether or not an agent is currently connected. We surface it as-is; we never build or store a key.
    try:
        body = json.dumps({'tool': 'remote_network_helper', 'args': {}}).encode()
        req = urllib.request.Request(DAEMON + '/tool', body, {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=3) as r:
            inner = json.loads(r.read()).get('result', '{}')
        st = json.loads(inner) if isinstance(inner, str) else inner
        out['command'] = st.get('agent_command_powershell') or st.get('launch_command_powershell')
        out['lan_ips'] = st.get('detected_lan_ips') or st.get('detected_master_lan_ips') or []
    except Exception:
        pass
    return out


class Portal(ThreadingHTTPServer):
    daemon_threads = True


def build_handler(lan_ip, data, sha, size):
    page = PAGE.replace('__SHA__', sha).replace('__SIZE__', f'{size // 1024} KB').replace('__IP__', html.escape(lan_ip))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _guard(self):
            try:
                if not ipaddress.ip_address(self.client_address[0]).is_private:
                    self.send_error(403); return False
            except ValueError:
                self.send_error(403); return False
            return True

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            for k, v in {'Content-Type': ctype, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                         'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                         'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'self'",
                         **(extra or {})}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._guard():
                return
            if self.path in ('/', '/index.html'):
                return self._send(200, page.encode(), 'text/html; charset=utf-8')
            if self.path == '/agent.exe':
                return self._send(200, data, 'application/octet-stream', {'Content-Disposition': 'attachment; filename="agent.exe"'})
            if self.path == '/api/state':
                return self._send(200, json.dumps(daemon_state()).encode(), 'application/json')
            self.send_error(404)

    return H


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenBridge Companion</title>
<style>
:root{--bg:#101419;--panel:#1a212a;--line:#394656;--text:#f5f0e3;--muted:#aebbc7;--accent:#ff6b1a;--ok:#5fd08a;--wait:#f5c06b}
*{box-sizing:border-box}html{color-scheme:dark}
body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#1b2633,var(--bg));color:var(--text);
font:15px/1.6 "Segoe UI",system-ui,sans-serif;min-height:100vh}
.wrap{max-width:720px;margin:0 auto;padding:40px 20px 60px}
.brand{display:flex;align-items:center;gap:10px;font-weight:650;font-size:22px;letter-spacing:-.5px}
.brand .m{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--accent);color:#14100b;font-size:18px}
.eyebrow{font:10px/1 ui-monospace,Consolas,monospace;letter-spacing:2px;color:var(--muted);margin:26px 0 8px}
h1{font-size:clamp(28px,5vw,40px);line-height:1.1;letter-spacing:-1px;margin:0 0 10px;font-weight:550}
.lede{color:var(--muted);margin:0 0 26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;margin:16px 0}
.card h2{font-size:13px;font:600 11px/1 ui-monospace,Consolas,monospace;letter-spacing:1.5px;color:var(--muted);margin:0 0 14px;text-transform:uppercase}
.step{display:flex;gap:12px;align-items:baseline}
.step .n{flex:none;width:24px;height:24px;border-radius:50%;background:#24303c;color:var(--accent);display:grid;place-items:center;font:600 12px/1 ui-monospace,monospace}
.btn{display:inline-flex;align-items:center;gap:10px;background:var(--accent);color:#14100b;border:0;border-radius:9px;
padding:15px 22px;font-weight:650;font-size:15px;cursor:pointer;text-decoration:none;transition:transform .08s,background .15s}
.btn:hover{background:#ff8c50}.btn:active{transform:translateY(1px)}
.btn.sec{background:transparent;color:var(--text);border:1px solid #64766d;padding:12px 16px;font-size:13px}
.btn.sec:hover{background:#263443}
.meta{font:11px/1.5 ui-monospace,Consolas,monospace;color:var(--muted);margin-top:12px;word-break:break-all}
.cmd{position:relative;margin-top:6px}
.cmd pre{background:#0c0f13;border:1px solid var(--line);border-radius:9px;padding:16px 56px 16px 16px;margin:0;
font:13px/1.5 ui-monospace,Consolas,monospace;color:#d6e0e8;white-space:pre-wrap;word-break:break-all;overflow:auto}
.copy{position:absolute;top:10px;right:10px;background:#24303c;border:1px solid var(--line);color:var(--text);
border-radius:7px;padding:8px 12px;font-size:12px;cursor:pointer;min-height:36px}
.copy:hover{background:#2c4052}.copy.done{background:#1f3a2a;border-color:#3f7a54;color:var(--ok)}
.live{display:flex;align-items:center;gap:12px}
.dot{flex:none;width:12px;height:12px;border-radius:50%;background:var(--wait);box-shadow:0 0 0 0 rgba(245,192,107,.5);animation:pulse 1.6s infinite}
.dot.ok{background:var(--ok);animation:none}.dot.off{background:#6b7682;animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(245,192,107,.5)}70%{box-shadow:0 0 0 10px rgba(245,192,107,0)}100%{box-shadow:0 0 0 0 rgba(245,192,107,0)}}
.live .big{font-size:17px;font-weight:600}.live .sub{font:11px/1.4 ui-monospace,monospace;color:var(--muted)}
.foot{color:var(--muted);font:10px/1.6 ui-monospace,Consolas,monospace;letter-spacing:1px;text-align:center;margin-top:30px}
.hint{font-size:12px;color:var(--muted);margin:8px 0 0}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:18px}
.mt{background:#0c0f13;border:1px solid var(--line);border-radius:9px;padding:12px 8px;text-align:center}
.mv{display:block;font:600 17px/1 ui-monospace,Consolas,monospace;color:var(--text)}
.ml{display:block;font:9px/1.3 ui-monospace,monospace;letter-spacing:.5px;color:var(--muted);margin-top:6px;text-transform:uppercase}
@media(max-width:520px){.metrics{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.wrap{padding:24px 14px}.btn{width:100%;justify-content:center}}
</style></head>
<body><div class="wrap">
<div class="brand"><span class="m">↗</span> OpenBridge <span style="color:var(--accent)">Companion</span></div>
<p class="eyebrow">OBSERVE · UNDERSTAND · VERIFY — READ-ONLY</p>
<h1>Connecter ce PC à OpenBridge</h1>
<p class="lede">Trois étapes, moins d'une minute. OpenBridge lira l'état de ce PC en lecture seule. Aucune commande, aucun fichier modifié.</p>

<div class="card"><h2>Étape 1 — Télécharger l'agent</h2>
<div class="step"><span class="n">1</span><div style="flex:1">
<a class="btn" href="/agent.exe" download>⬇ Télécharger agent.exe <span style="opacity:.7;font-weight:400">· __SIZE__</span></a>
<p class="meta">SHA-256 : __SHA__</p></div></div></div>

<div class="card"><h2>Étape 2 — Lancer l'agent</h2>
<div class="step"><span class="n">2</span><div style="flex:1">
<p class="hint">Ouvre PowerShell dans le dossier du fichier téléchargé, puis colle&nbsp;:</p>
<div class="cmd"><pre id="cmd">Chargement de la commande…</pre><button class="copy" id="copy">Copier</button></div>
<p class="hint" id="cmdhint">La commande connecte l'agent à ce PC (OpenBridge) à l'adresse __IP__.</p></div></div></div>

<div class="card"><h2>Étape 3 — Vérification en direct</h2>
<div class="step"><span class="n">3</span><div style="flex:1" class="live">
<span class="dot" id="dot"></span><div><div class="big" id="state">En attente du PC…</div>
<div class="sub" id="statesub">Cette page se met à jour automatiquement.</div></div></div>
<div class="metrics" id="metrics" hidden>
<div class="mt"><span class="mv" id="m-cpu">—</span><span class="ml">CPU</span></div>
<div class="mt"><span class="mv" id="m-ram">—</span><span class="ml">RAM utilisée</span></div>
<div class="mt"><span class="mv" id="m-disk">—</span><span class="ml">Disque libre</span></div>
<div class="mt"><span class="mv" id="m-up">—</span><span class="ml">Uptime</span></div>
<div class="mt"><span class="mv" id="m-rtt">—</span><span class="ml">Latence</span></div>
</div></div></div>

<p class="foot">OPENBRIDGE · LECTURE SEULE · CETTE PAGE S'ARRÊTE TOUTE SEULE</p>
</div>
<script>
var cmdEl=document.getElementById('cmd'),copyBtn=document.getElementById('copy'),
dot=document.getElementById('dot'),stateEl=document.getElementById('state'),
subEl=document.getElementById('statesub'),hintEl=document.getElementById('cmdhint'),
metrics=document.getElementById('metrics'),lastCmd='';
function fmt(v,suf){return (v===null||v===undefined)?'—':(v+suf);}
function setMetrics(m){
  if(!m){metrics.hidden=true;return;}metrics.hidden=false;
  document.getElementById('m-cpu').textContent=fmt(m.cpu,'%')+(m.cores?(' · '+m.cores+'c'):'');
  document.getElementById('m-ram').textContent=fmt(m.ram_used_pct,'%');
  document.getElementById('m-disk').textContent=fmt(m.disk_free_gb,' Go');
  document.getElementById('m-up').textContent=fmt(m.uptime_h,' h');
  document.getElementById('m-rtt').textContent=fmt(m.rtt_ms?Math.round(m.rtt_ms):null,' ms');
}
function copyText(t){
  if(navigator.clipboard&&window.isSecureContext){return navigator.clipboard.writeText(t);}
  return new Promise(function(res,rej){var a=document.createElement('textarea');a.value=t;
  a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.focus();a.select();
  try{document.execCommand('copy');res();}catch(e){rej(e);}document.body.removeChild(a);});
}
copyBtn.onclick=function(){if(!lastCmd)return;copyText(lastCmd).then(function(){
  copyBtn.textContent='Copié ✓';copyBtn.classList.add('done');
  setTimeout(function(){copyBtn.textContent='Copier';copyBtn.classList.remove('done');},1800);
}).catch(function(){copyBtn.textContent='Sélectionne et copie';});};
function poll(){
  fetch('/api/state',{cache:'no-store'}).then(function(r){return r.json();}).then(function(s){
    if(s.command){lastCmd=s.command;cmdEl.textContent=s.command;}
    else if(!lastCmd){cmdEl.textContent='agent.exe --host __IP__ --port 9876 --token <VOTRE_CLE>';lastCmd=cmdEl.textContent;}
    if(s.connected){
      dot.className='dot ok';
      stateEl.textContent='Connecté ✓';
      subEl.textContent='Agent '+(s.arch||'')+' · v'+(s.version||'?')+' · OpenBridge peut lire ce PC.';
      setMetrics(s.metrics);
    }else{setMetrics(null);
      dot.className='dot';stateEl.textContent='En attente du PC…';
      subEl.textContent='Lance la commande de l\'étape 2 sur l\'autre PC.';
    }
  }).catch(function(){setMetrics(null);dot.className='dot off';stateEl.textContent='Portail actif';
    subEl.textContent='Démarre le service OpenBridge pour voir l\'état en direct.';});
}
poll();setInterval(poll,2000);
</script>
</body></html>"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    lan_ip, port, exe = args[0], int(args[1]), Path(args[2])
    minutes = 45
    if '--minutes' in sys.argv:
        minutes = int(sys.argv[sys.argv.index('--minutes') + 1])
    data = exe.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    srv = Portal((lan_ip, port), build_handler(lan_ip, data, sha, len(data)))
    threading.Timer(minutes * 60, srv.shutdown).start()
    print(f'PORTAL http://{lan_ip}:{port}/  serving {exe.name} ({len(data)//1024} KB) sha256={sha} for {minutes} min', flush=True)
    srv.serve_forever()
    print('PORTAL stopped', flush=True)


if __name__ == '__main__':
    main()
