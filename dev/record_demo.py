"""Captioned evidence-only browser recording; no desktop input, provider calls or physical writes."""
from datetime import datetime
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
from playwright.sync_api import sync_playwright, expect
from src.adapters.simulated_setting import SimulatedSetting
from src.core.transactions import TransactionEngine
from src.server import create_server


def main():
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    output=Path('artifacts')/('demo-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True,exist_ok=False)
    with TemporaryDirectory() as directory:
        adapter=SimulatedSetting(Path(directory)/'setting.sqlite')
        engine=TransactionEngine(Path(directory)/'journal.sqlite',adapter)
        server=create_server(0,demo_engine=engine)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_port}'
        scenes=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                context=browser.new_context(viewport={'width':1920,'height':1080},
                    record_video_dir=str(output),record_video_size={'width':1920,'height':1080})
                page=context.new_page()
                page.goto(url,wait_until='networkidle')
                started=time.monotonic()
                def caption(text):
                    page.evaluate('''text=>{
                        let box=document.getElementById('recording-caption');
                        if(!box){box=document.createElement('div');box.id='recording-caption';document.body.append(box);}
                        Object.assign(box.style,{position:'fixed',left:'48px',right:'48px',bottom:'24px',padding:'24px 32px',
                            background:'rgba(10,15,20,0.96)',color:'#f5f0e3',borderLeft:'6px solid #ff6b1a',
                            fontFamily:'Segoe UI, sans-serif',fontSize:'34px',fontWeight:'500',lineHeight:'1.35',
                            zIndex:'2147483647',pointerEvents:'none',boxShadow:'0 8px 30px #0008'});
                        box.textContent=text;
                    }''',text)
                def hold(until):
                    remaining=until-(time.monotonic()-started)
                    if remaining>0:time.sleep(remaining)
                def scene(name,text):
                    caption(text);scenes.append({'at_seconds':round(time.monotonic()-started,2),'name':name,'caption':text})
                    print(f'Scene: {name}',flush=True)
                scene('problem','USB phones and local gateways expose different permissions. OpenBridge makes their facts, sources and limits visible.')
                hold(12)
                page.get_by_role('radio',name='Android USB').check()
                page.get_by_role('button',name='List USB devices').click()
                inspect=page.get_by_role('button',name='Inspect evidence').first
                expect(inspect).to_be_visible(timeout=15000)
                inspect.click()
                page.get_by_text('Reading complete. No device was changed.',exact=True).wait_for(timeout=60000)
                page.locator('#report').scroll_into_view_if_needed()
                scene('real-android','A real, authorized USB phone. These facts are read from Android; private device identifiers stay hidden.')
                hold(33)
                page.get_by_role('radio',name='Simulated demo').check()
                page.get_by_role('button',name='View recorded Meta proof').click()
                page.get_by_text('RECORDED RUN',exact=False).wait_for()
                page.locator('#recorded-proof-result').scroll_into_view_if_needed()
                scene('recorded-meta','Meta Muse Spark 1.3: a real recorded runtime-core inference on synthetic facts. Viewing this proof makes no new API call.')
                hold(49)
                scene('meta-boundaries','The model result carries evidence references and uncertainty. Physical device data stays local; default cloud requests are blocked.')
                hold(65)
                page.locator('#demo-consent').check()
                page.get_by_role('button',name='Run simulated change').click()
                expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · VERIFIED.')
                page.locator('#transaction-result').scroll_into_view_if_needed()
                scene('simulated-change','SIMULATED recovery sandbox: save the exact original value, apply a bounded change, then verify the read-back. No phone setting changes here.')
                hold(89)
                page.reload(wait_until='networkidle')
                undo=page.get_by_role('button',name='Undo simulated change');expect(undo).to_be_enabled()
                undo.scroll_into_view_if_needed()
                scene('durable-recovery','After a page reload, the saved transaction still exists. The original value has not been lost.')
                hold(99)
                undo.click()
                expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · REVERTED.')
                scene('simulated-undo','SIMULATED Undo restores the exact saved value. This demonstrates durable recovery, not physical-device rollback.')
                hold(111)
                page.get_by_role('radio',name='Freebox gateway').check()
                page.get_by_role('button',name='Identify local Freebox').click()
                gateway=page.get_by_role('button',name='Inspect evidence');expect(gateway).to_be_visible(timeout=10000);gateway.click()
                page.get_by_text('Reading complete. No device was changed.',exact=True).wait_for()
                page.locator('#report').scroll_into_view_if_needed()
                scene('real-gateway','A second real protocol: Freebox public identity discovery. No pairing, credentials or router configuration is used.')
                hold(135)
                proof_url=f'https://raw.githubusercontent.com/toskaman/openbridge/{revision}/docs/physical-transaction-attempt.json'
                page.goto(proof_url,wait_until='domcontentloaded',timeout=20000)
                expect(page.locator('body')).to_contain_text('PHYSICAL_WRITE_BLOCKED')
                page.evaluate('''()=>{Object.assign(document.body.style,{background:'#101419',color:'#f5f0e3',fontSize:'23px',padding:'30px',lineHeight:'1.5'});
                    for(const pre of document.querySelectorAll('pre'))Object.assign(pre.style,{fontSize:'23px',whiteSpace:'pre-wrap'});}''')
                scene('real-refusal-record','RECORDED PHYSICAL ATTEMPT: Android refused the write. A separate read confirmed the original setting remained intact. Physical Undo success is not claimed.')
                hold(155)
                page.goto(url,wait_until='networkidle')
                scene('validation','71 unit/integration tests. Green Windows, Linux and offline-browser CI. Event-created source and sanitized evidence are public on GitHub.')
                hold(166)
                scene('closing','OpenBridge · github.com/toskaman/openbridge. Read-only physical devices. Verified simulated recovery. Meta Muse Spark 1.3 design and runtime evidence.')
                hold(174)
                video=page.video
                context.close()
                video_path=video.path()
                browser.close()
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)
    manifest={'source_revision':revision,'capture':'Actual headless app browser session; no desktop input',
              'language':'English','audio':'Intentionally silent; burned-in English captions',
              'claims':'Real read-only Android and gateway; recorded Meta proof; simulated recovery; recorded blocked physical write',
              'raw_video':str(video_path),'scenes':scenes,'physical_write_requests_during_capture':0,'model_requests_during_capture':0}
    (output/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Capture complete: {output}',flush=True)


if __name__=='__main__':
    main()
