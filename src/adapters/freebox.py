"""Public Freebox identity discovery only; no pairing or authenticated control."""
from datetime import datetime, timezone
import json
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

DISCOVERY_URL = 'http://mafreebox.freebox.fr/api_version'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_discovery():
    request=Request(DISCOVERY_URL, headers={'Accept':'application/json'}, method='GET')
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=4) as response:
        data=response.read(16385)
        if len(data)>16384:
            raise ValueError('Discovery response too large')
        return json.loads(data)


class FreeboxAdapter:
    def __init__(self, fetch=fetch_discovery):
        self.fetch=fetch

    def _facts(self):
        data=self.fetch()
        if not isinstance(data,dict):
            raise ValueError('Invalid gateway response')
        api_version=data.get('api_version','')
        device_type=data.get('device_type','')
        if (not isinstance(api_version,str) or not re.fullmatch(r'\d{1,3}\.\d{1,3}',api_version)
                or not isinstance(device_type,str) or not re.fullmatch(r'FreeboxServer\d{1,3},\d{1,3}',device_type)
                or data.get('api_base_url') != '/api/'):
            raise ValueError('Unsupported gateway discovery response')
        return {'api_version':api_version,'device_family':device_type,'api_base_path':'/api/'}

    def discover(self):
        try:
            facts=self._facts()
            return {'status':'READY','devices':[{
                'id':'freebox-local','name':'Local Freebox gateway','state':'device',
                'source':'FREEBOX_DISCOVERY','transport':'LOCAL HTTP','simulated':False,
                'capabilities':['inspect'],'observed_at':datetime.now(timezone.utc).isoformat(),
                'facts':facts,'access_scope':'PUBLIC_IDENTITY_ONLY'}]}
        except (OSError,ValueError,TypeError):
            return {'status':'GATEWAY_UNAVAILABLE','devices':[]}

    def inspect(self, handle):
        if handle != 'freebox-local':
            raise ValueError('Unknown gateway')
        inventory=self.discover()
        if not inventory['devices']:
            raise ValueError('Gateway unavailable; no discovery evidence collected')
        device=inventory['devices'][0]
        return {'device_id':handle,'status':'READ_ONLY','simulated':False,
                'source':'FREEBOX_DISCOVERY','model_status':'NOT_CONNECTED',
                'observed_at':device['observed_at'],
                'summary':'Freebox public identity verified. No pairing or authenticated router access.',
                'evidence':[{'key':k,'value':v,'source':'FREEBOX_DISCOVERY','observed_at':device['observed_at']} for k,v in device['facts'].items()],
                'checks':[
                    {'name':'Public discovery','status':'PASS','detail':'Read the documented API version endpoint only.'},
                    {'name':'Router settings','status':'BLOCKED','detail':'No credentials, pairing or configuration access.'},
                    {'name':'Meta inference','status':'NOT_TESTED','detail':'Gateway data stays local.'},
                    {'name':'Physical rollback','status':'NOT_TESTED','detail':'No settings were changed.'}]}
