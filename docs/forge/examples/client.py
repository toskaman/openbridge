"""Fixed read-only local client; supply token separately."""
import json
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
def read_observations(token):
    req=Request('http://127.0.0.1:18766/v1/services/ble-observations/observations',headers={"Authorization":"Bearer "+token})
    with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=5) as response:
        return json.loads(response.read(131072))
