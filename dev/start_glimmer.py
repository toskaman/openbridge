"""Start a separate private Ollama service (GPU/CPU offload) and optionally pull pinned Meta Muse Glimmer."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import Request,build_opener,ProxyHandler

HOST='http://127.0.0.1:11438'
MODEL='muse-glimmer:30b-q4_K_M'
DIGEST='de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pull-model',action='store_true')
    args=parser.parse_args()
    executable=shutil.which('ollama')
    if not executable:raise SystemExit('Ollama is not installed')
    with socket.socket() as check:
        try:check.bind(('127.0.0.1',11438))
        except OSError:raise SystemExit('Private Meta service port is occupied; no process was changed')
    private=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'OpenBridge'/'glimmer'
    private.mkdir(parents=True,exist_ok=True)
    allowed={'PATH','SYSTEMROOT','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP','COMSPEC','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','PATHEXT','SYSTEMDRIVE'}
    environment={key:value for key,value in os.environ.items() if key.upper() in allowed}
    environment.update(OLLAMA_HOST='127.0.0.1:11438',OLLAMA_MODELS=str(private/'models'),
OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',
        OLLAMA_CONTEXT_LENGTH='4096',OLLAMA_KEEP_ALIVE='60s',OLLAMA_NO_CLOUD='1')
    log=(private/'service.log').open('ab')
    process=subprocess.Popen([executable,'serve'],env=environment,stdout=log,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log.close()
    opener=build_opener(ProxyHandler({}))
    ready=False
    for _ in range(60):
        if process.poll() is not None:break
        try:
            with opener.open(HOST+'/api/tags',timeout=1):ready=True;break
        except OSError:time.sleep(0.25)
    if not ready:
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        raise SystemExit('Private Meta service did not start; unrelated services were left untouched')
    (private/'service.json').write_text(json.dumps({'pid':process.pid,'endpoint':HOST,'model':MODEL,'cpu_only_requested':False}),encoding='utf-8')
    print('Private Meta service ready on loopback port 11438. Existing Ollama service was not modified.',flush=True)
    if args.pull_model:
        request=Request(HOST+'/api/pull',data=json.dumps({'model':MODEL,'stream':True}).encode(),headers={'Content-Type':'application/json'},method='POST')
        previous=None
        with opener.open(request,timeout=7200) as response:
            for line in response:
                item=json.loads(line)
                if 'error' in item:raise SystemExit('Pinned Meta model download failed; inspect the private service log')
                total=item.get('total',0);completed=item.get('completed',0)
                progress=int(completed*100/total)//25*25 if total else None
                signal=(item.get('status'),progress)
                if signal!=previous:
                    print('Model download:',item.get('status',''),f'{progress}%' if progress is not None else '',flush=True)
                    previous=signal
    with opener.open(HOST+'/api/tags',timeout=3) as response:catalog=json.load(response)
    match=next((row for row in catalog.get('models',[]) if row.get('name')==MODEL),None)
    if not match or match.get('digest','').removeprefix('sha256:')!=DIGEST:
        raise SystemExit('Pinned Meta model is unavailable or has an unexpected digest; inference remains blocked')
    print('Official Meta Muse Glimmer manifest digest verified. No inference was performed.',flush=True)


if __name__=='__main__':
    main()
