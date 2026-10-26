"""Owner-authorized test helper: pair the Companion over USB (adb forward), reading the on-screen code via uiautomator."""
import json, re, subprocess, sys, time, secrets
from pathlib import Path
from src.adapters.android import AndroidAdapter
from src.fabric import relay as R

serial=sys.argv[1] if len(sys.argv)>1 else None
if serial and ':' in serial:
    send=R.http_transport('http://'+serial.split(':')[0]+':47800')   # LAN relay (TV)
else:
    a=AndroidAdapter();d=[x for x in a.discover()['devices'] if x['state']=='device' and x['transport']=='USB'][0]
    serial=next(k for k,v in a._handles.items() if v==d['id']);send=R.http_transport(a.forward_companion(d['id']))
pc=secrets.token_hex(16);hello=send(None,{'op':'pair_request','pc_nonce':pc})
print('hello',hello['relay_id'],json.dumps(hello.get('declared')))
time.sleep(1.5)
subprocess.run(['adb','-s',serial,'shell','uiautomator','dump','/sdcard/ob_ui.xml'],capture_output=True)
xml=subprocess.run(['adb','-s',serial,'shell','cat','/sdcard/ob_ui.xml'],capture_output=True,text=True,encoding='utf-8').stdout
subprocess.run(['adb','-s',serial,'shell','rm','/sdcard/ob_ui.xml'],capture_output=True)
m=re.search(r'Pairing code (\d{6})',xml)
code=next(g for g in m.groups() if g) if m else None
print('code_found',bool(code))
if not code:sys.exit('code not readable')
key=R.derive_key(code,hello['relay_nonce'],pc)
declared=R.verify(key,send(None,R.command(key,hello['relay_id'],'discover_capabilities')),set())['params']
print('PAIRED',json.dumps(declared))
Path(Path.home()/('AppData/Local/OpenBridge/relay-test'+('-tv' if ':' in serial else '')+'.json')).write_text(json.dumps({'relay_id':hello['relay_id'],'key':key.hex()}))
