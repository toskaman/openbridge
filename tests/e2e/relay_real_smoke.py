import os
"""Real-hardware relay UI check (not CI): server on 127.0.0.1:18799, phone with the Companion open and scans enabled.
The pairing code is read from the phone screen via uiautomator (owner-authorized test automation)."""
import re, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def screen_code(serial):
    for _ in range(10):
        subprocess.run(['adb','-s',serial,'shell','uiautomator','dump','/sdcard/ob_ui.xml'],capture_output=True)
        xml=subprocess.run(['adb','-s',serial,'shell','cat','/sdcard/ob_ui.xml'],capture_output=True,text=True,encoding='utf-8').stdout
        m=re.search(r'Pairing code (\d{6})',xml)
        if m:
            subprocess.run(['adb','-s',serial,'shell','rm','/sdcard/ob_ui.xml'],capture_output=True);return m.group(1)
        time.sleep(1)
    raise SystemExit('code not visible')

def main(serial=os.environ.get('OPENBRIDGE_PHONE_SERIAL',''),node='2107113SG',tag='phone'):
    out=Path('artifacts/relay');out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1100});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:18799/?redact#/devices',wait_until='networkidle')
        page.get_by_role('button',name='Discover my environment').click()
        page.get_by_role('button',name='Topology list').click()
        expect(page.locator('#fabric-meta')).to_contain_text('DEVICE(S)',timeout=60000)
        page.locator('#fabric-tree .fabric-node',has_text=node).first.click()
        page.get_by_role('button',name='Use as Bluetooth relay').click()
        expect(page.locator('#relay-code')).to_be_visible(timeout=20000)
        page.locator('#relay-code').fill(screen_code(serial))
        page.get_by_role('button',name='Pair',exact=True).click()
        expect(page.locator('.relay-panel')).to_contain_text('Paired',timeout=20000)
        page.screenshot(path=str(out/f'{tag}-1440-paired.png'))
        page.get_by_role('button',name='Scan nearby Bluetooth (8 s)').click()
        expect(page.locator('#fabric-providers')).to_contain_text('RELAY: OK',timeout=40000)
        expect(page.locator('#fabric-detail p',has_text='ble_relay')).to_contain_text('REAL_HARDWARE_VERIFIED')
        page.locator('#fabric').screenshot(path=str(out/f'{tag}-1440-relayed.png'))
        ble=page.locator('#fabric-tree .fabric-node',has_text='BLE')
        tvs=page.locator('#fabric-tree .fabric-node .cat',has_text='tv').count()
        print('tv_nodes',tvs,'ble_nodes',ble.count(),'|',page.locator('#fabric-providers').inner_text().replace('\n',' | '))
        assert ble.count()>=1 and not errors,errors
        b.close()

if __name__=='__main__':
    import sys;main(*sys.argv[1:])
