import json
from src.adapters.freebox import FreeboxAdapter
from src.adapters.freebox_auth import FreeboxSession
from src.fabric.credential_vault import Vault
from src.runtime.diagnostics import freebox
f=FreeboxAdapter().discover()['devices'][0]['facts'];s=FreeboxSession(Vault(),f['api_version'].split('.')[0])
for x in freebox(s):print(x['kind'],x['level'],x['name'],x['value'],x['unit'])
