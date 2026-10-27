"""Test-only startup guard copied into a disposable integration build as sitecustomize.py."""
import ipaddress,json,os,socket,subprocess
from pathlib import Path

def denied(kind):
    with open(os.environ['OPENBRIDGE_TEST_GUARD_LOG'],'a',encoding='utf-8') as log:log.write(json.dumps({'blocked':kind})+'\n')
    raise AssertionError('Controlled test attempted forbidden I/O: '+kind)

def allowed_host(host):
    if isinstance(host,bytes):host=host.decode('ascii',errors='replace')
    if host in ('localhost',''):return True
    try:return ipaddress.ip_address(host).is_loopback
    except ValueError:return False

def check_address(address):
    if not isinstance(address,tuple):return
    if not allowed_host(address[0]):denied('NON_LOOPBACK_SOCKET')
    if len(address)>1 and address[1] in (11434,11437,11438,11439):denied('ACTUAL_MODEL_SOCKET')

_getaddrinfo=socket.getaddrinfo

def getaddrinfo(host,*args,**kwargs):
    if host is not None and not allowed_host(host):denied('NON_LOOPBACK_DNS')
    return _getaddrinfo(host,*args,**kwargs)
socket.getaddrinfo=getaddrinfo
_connect=socket.socket.connect
_connect_ex=socket.socket.connect_ex
_sendto=socket.socket.sendto

def connect(self,address):check_address(address);return _connect(self,address)
def connect_ex(self,address):check_address(address);return _connect_ex(self,address)
def sendto(self,data,*args):
    if args:check_address(args[-1])
    return _sendto(self,data,*args)
socket.socket.connect=connect;socket.socket.connect_ex=connect_ex;socket.socket.sendto=sendto
_popen=subprocess.Popen

class GuardedPopen(_popen):
    def __init__(self,args,*positional,**kwargs):
        first=args[0] if isinstance(args,(list,tuple)) and args else args
        if isinstance(first,(str,bytes,os.PathLike)):
            name=Path(os.fsdecode(first)).name.lower()
            if name in ('adb','adb.exe') and not (isinstance(args,(list,tuple)) and len(args)==2 and args[1]=='version'):
                denied('ACTUAL_ADB_DEVICE_COMMAND')
        super().__init__(args,*positional,**kwargs)
subprocess.Popen=GuardedPopen
GUARD_READY=True
