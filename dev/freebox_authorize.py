"""Owner-run: request official Freebox app authorization, wait for the front-panel button, store token via DPAPI."""
import json, time, sys
from pathlib import Path
from src.adapters.freebox import FreeboxAdapter
from src.adapters.freebox_auth import FreeboxSession
from src.fabric.credential_vault import Vault

facts=FreeboxAdapter().discover()['devices'][0]['facts']
major=facts['api_version'].split('.')[0]
s=FreeboxSession(Vault(),major)
status_file=Path('artifacts/freebox_auth_status.json')
def report(state):status_file.write_text(json.dumps({'state':state,'at':time.strftime('%H:%M:%S')}));print(state,flush=True)
if s.state()=='AUTHORIZED':report('ALREADY_AUTHORIZED');sys.exit(0)
s.request_authorization();report('PENDING_PRESS_BUTTON_ON_FREEBOX')
deadline=time.monotonic()+480
while time.monotonic()<deadline:
    st=s.poll_authorization()
    if st in ('granted','denied','timeout'):report(st.upper());break
    time.sleep(2)
else:report('GAVE_UP_AFTER_8_MIN')
