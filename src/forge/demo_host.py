"""Standalone simulated Forge integration host. Does not modify the main server."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import time
from src.forge.compiler import ForgeError
from src.forge.fixtures import manifest
from src.forge.service import ForgeService,MemoryProvider
from src.forge.planner import rules_plan

UI=Path(__file__).parent/'ui'
ASSETS={'/':('index.html','text/html; charset=utf-8'),'/forge.css':('forge.css','text/css; charset=utf-8'),'/forge.js':('forge.js','text/javascript; charset=utf-8')}

class ForgeServer(ThreadingHTTPServer):
    daemon_threads=True
    def server_close(self):
        self.forge.close();super().server_close()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass  # Never log bearer headers, names or observations.
    def reply(self,code,value,mime='application/json'):
        body=json.dumps(value,allow_nan=False).encode() if mime=='application/json' else value
        self.send_response(code)
        for key,val in {'Content-Type':mime,'Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"}.items():self.send_header(key,val)
        self.end_headers();self.wfile.write(body)
    def guard(self,mutation=False):
        expected='127.0.0.1:'+str(self.server.server_port)
        if self.headers.get('Host')!=expected:self.reply(403,{'error':'HOST_DENIED'});return False
        if mutation and self.headers.get('Origin')!='http://'+expected:self.reply(403,{'error':'ORIGIN_DENIED'});return False
        return True
    def authorized(self):
        if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token):self.reply(401,{'error':'AUTHENTICATION_REQUIRED'});return False
        return True
    def do_GET(self):
        if not self.guard():return
        if self.path in ASSETS:
            name,mime=ASSETS[self.path];return self.reply(200,(UI/name).read_bytes(),mime)
        if self.path=='/api/session':return self.reply(200,{'token':self.server.token,'scope':'local-simulated-forge'})
        if not self.authorized():return
        try:
            if self.path=='/api/catalog':return self.reply(200,{'manifest':self.server.provider.snapshot('tv.ble.observations'),'services':self.server.forge.list_services(),'history':self.server.forge.history(),'mode':'SIMULATED','glimmer_configured':self.server.planner is not None})
            if self.path=='/api/documents':return self.reply(200,self.server.forge.documents('ble-observations'))
            if self.path=='/v1/services/ble-observations/observations':return self.reply(200,self.server.forge.read('ble-observations'))
        except ForgeError as e:return self.reply(404 if str(e)=='SERVICE_REMOVED' else 409,{'error':str(e)})
        self.reply(404,{'error':'UNKNOWN_ROUTE'})
    def do_POST(self):
        if not self.guard(True) or not self.authorized():return
        if self.path not in ('/api/publish','/api/remove','/api/plan'):return self.reply(404,{'error':'UNKNOWN_ROUTE'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if self.headers.get('Transfer-Encoding') or not 0<length<=8192:return self.reply(413,{'error':'BODY_SIZE_DENIED'})
            body=json.loads(self.rfile.read(length));
            if not isinstance(body,dict):raise ForgeError('INVALID_BODY')
            if self.path=='/api/publish':
                if set(body)!={'consent'}:raise ForgeError('INVALID_BODY')
                return self.reply(200,self.server.forge.publish(self.server.provider.snapshot('tv.ble.observations'),consent=body['consent']))
            if self.path=='/api/remove':
                if body!={}:raise ForgeError('INVALID_BODY')
                self.server.forge.remove('ble-observations');return self.reply(200,{'state':'removed'})
            if set(body)!={'planner'} or body['planner'] not in ('rules','glimmer'):raise ForgeError('INVALID_BODY')
            snapshots=[self.server.provider.snapshot('tv.ble.observations')]
            if body['planner']=='rules':return self.reply(200,{'plan':rules_plan(snapshots,time.time()),'source':'RULES','authorizes_execution':False})
            if self.server.planner is None:return self.reply(409,{'error':'META_UNAVAILABLE: local Glimmer is not configured; no fallback made'})
            return self.reply(200,self.server.planner.plan(snapshots,time.time()))
        except (ValueError,KeyError,TypeError) as e:
            return self.reply(409 if isinstance(e,ForgeError) and str(e)!='INVALID_BODY' else 400,{'error':str(e) if isinstance(e,ForgeError) else 'INVALID_BODY'})

def create_forge_server(port=18766,planner=None):
    server=ForgeServer(('127.0.0.1',port),Handler)
    server.token=secrets.token_urlsafe(32);server.provider=MemoryProvider(manifest());server.forge=ForgeService(server.provider);server.planner=planner
    return server

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=18766);p.add_argument('--glimmer',action='store_true');args=p.parse_args()
    planner=None
    if args.glimmer:
        from src.ai.glimmer import GlimmerBroker
        from src.forge.meta_planner import MetaCapabilityPlanner
        planner=MetaCapabilityPlanner(GlimmerBroker())
    with create_forge_server(args.port,planner) as server:
        print(f'Capability Forge: http://127.0.0.1:{server.server_port} — SIMULATED, no hardware access',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=='__main__':main()
