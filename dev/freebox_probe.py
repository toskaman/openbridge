"""Owner-authorized: which read-only Freebox endpoints answer with the current app token (GET only). Prints shapes, not values."""
import json
from src.adapters.freebox import FreeboxAdapter
from src.adapters import freebox_auth as F
from src.fabric.credential_vault import Vault
facts=FreeboxAdapter().discover()['devices'][0]['facts'];s=F.FreeboxSession(Vault(),facts['api_version'].split('.')[0])
print('state',s.state())
if s.state()=='AUTHORIZED':
    F.READ_ONLY_PATHS=F.READ_ONLY_PATHS+('wifi/ap/','wifi/bss/','wifi/config/','lan/config/','connection/full/','connection/ftth/','dhcp/config/','system/')
    for p in ('connection/','connection/full/','connection/ftth/','system/','lan/config/','wifi/config/','wifi/ap/','wifi/bss/'):
        try:r=s.get(p);print(p,'OK',sorted(r)[:14] if isinstance(r,dict) else f'list[{len(r)}]')
        except Exception as e:print(p,'NO',str(e)[:60])
