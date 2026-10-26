"""Hermetic Device Fabric UI check at four widths: controlled discovery response, zero network or device calls."""
import threading
from playwright.sync_api import sync_playwright, expect
from src.server import create_server

SNAP={'schema_version':1,'elapsed_ms':12,'providers':{'mdns':{'status':'OK','instances':3,'packets':3},'ble':{'status':'BLE_UNAVAILABLE','devices':0},'freebox':{'status':'PUBLIC_ONLY','authorization':'NOT_AUTHORIZED','lan_hosts':0}},
 'devices':[{'key':'dev-box','category':'router','label':'Freebox','identifier_kinds':['freebox_uid'],'facts':{'api_version':{'value':'16.1','sources':['FREEBOX_API'],'verified':True}},
             'capabilities':[{'name':'lan_inventory','level':'read','status':'BLOCKED','via':'FREEBOX_API','evidence':'not_authorized'}],'possibly_same_as':[],'last_seen':''},
            {'key':'dev-tv','category':'tv','label':'Living room TV','identifier_kinds':[],'facts':{},'capabilities':[],'possibly_same_as':['dev-cast'],'last_seen':''},
            {'key':'dev-cast','category':'media','label':'Cast','identifier_kinds':['cast_id'],'facts':{},'capabilities':[],'possibly_same_as':['dev-tv'],'last_seen':''},
            {'key':'dev-phone','category':'phone','label':'Test phone','identifier_kinds':['android_serial'],'facts':{},'handles':{'USB':'android-x'},
             'capabilities':[{'name':'ble_relay','level':'observe','status':'NOT_SUPPORTED','via':'USB','evidence':'requires OpenBridge Companion'}],'possibly_same_as':[],'last_seen':''},
            {'key':'dev-ble','category':'ble','label':'Thermometer','identifier_kinds':[],'facts':{},'capabilities':[],'possibly_same_as':[],'last_seen':''}],
 'links':[{'parent':'pc','child':'dev-box','transport':'LAN','grants':['read'],'source':'FREEBOX_API:public'},{'parent':'pc','child':'dev-box','transport':'LAN','grants':['observe'],'source':'MDNS:_http._tcp'},
          {'parent':'pc','child':'dev-tv','transport':'LAN','grants':['observe'],'source':'MDNS'},{'parent':'pc','child':'dev-cast','transport':'LAN','grants':['observe'],'source':'MDNS'},
          {'parent':'pc','child':'dev-phone','transport':'USB','grants':['read','control'],'source':'ADB:device'},
          {'parent':'dev-tv','child':'dev-ble','transport':'BLE','grants':['observe'],'source':'RELAY:tv'}],'possible_duplicates':[['dev-cast','dev-tv']]}


def main():
    server=create_server(0,fabric_salt=b'e2e');w=threading.Thread(target=server.serve_forever,daemon=True);w.start()
    try:
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True)
            for width in (390,768,1440,3440):
                page=b.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/fabric-discover',lambda r:r.fulfill(json=SNAP))
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
                page.get_by_role('button',name='Discover my environment').click()
                expect(page.locator('#fabric-meta')).to_contain_text('5 DEVICE(S)')
                expect(page.get_by_role('button',name='Authorize read-only Freebox inventory')).to_be_visible()
                box=page.locator('#fabric-tree .fabric-node',has_text='Freebox');expect(box.locator('.grant')).to_have_count(1)
                expect(page.locator('#fabric-tree')).to_contain_text('possible duplicate')
                page.locator('#fabric-tree .fabric-node',has_text='Thermometer').click()   # indirect device under the TV relay
                expect(page.locator('#fabric-detail')).to_contain_text('Observed only')
                page.locator('#fabric-tree .fabric-node',has_text='Living room TV').click()
                expect(page.locator('#fabric-detail')).to_contain_text('not merged')
                import copy
                relayed=copy.deepcopy(SNAP);relayed['providers']['relay']={'status':'OK','devices':1}
                relayed['devices'][3]['capabilities']=[{'name':'ble_relay','level':'observe','status':'REAL_HARDWARE_VERIFIED','via':'RELAY:r1','evidence':'1 advertisers reported'}]
                relayed['devices'].append({'key':'dev-buds','category':'ble','label':'Apple device (BLE)','identifier_kinds':[],'facts':{},'capabilities':[],'possibly_same_as':[],'last_seen':''})
                relayed['links'].append({'parent':'dev-phone','child':'dev-buds','transport':'BLE','grants':['observe'],'source':'RELAY:r1'})
                page.route('**/api/relay-pair-start',lambda r:r.fulfill(json={'state':'CODE_SHOWN_ON_DEVICE','relay_id':'r1','declared':{}}))
                page.route('**/api/relay-pair-confirm',lambda r:r.fulfill(json={'state':'PAIRED','relay_id':'r1','eligible_for_ble':True,'declared':{'permissions':{}}}))
                page.route('**/api/relay-scan',lambda r:r.fulfill(json=relayed))
                page.locator('#fabric-tree .fabric-node',has_text='Test phone').click()
                page.get_by_role('button',name='Use as Bluetooth relay').click()
                page.locator('#relay-code').fill('123456');page.get_by_role('button',name='Pair',exact=True).click()
                page.get_by_role('button',name='Scan nearby Bluetooth (8 s)').click()
                expect(page.locator('#fabric-tree')).to_contain_text('Apple device (BLE)')
                expect(page.locator('#fabric-detail')).to_contain_text('REAL_HARDWARE_VERIFIED');expect(page.locator('#fabric-detail')).not_to_contain_text('NOT_SUPPORTED')
                page.route('**/api/relay-scan',lambda r:r.fulfill(status=409,json={'error':'Relay refused: Bluetooth is off on this device','guide':{'issue':'bluetooth_off','vendor':'xiaomi','title':'Turn Bluetooth on','why':'w','tried':['scan'],'steps':['s1'],'waiting':'x'}}))
                page.get_by_role('button',name='Scan nearby Bluetooth (8 s)').click()
                expect(page.locator('#guide')).to_contain_text('Turn Bluetooth on')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                page.close()
            b.close()
    finally:
        server.shutdown();server.server_close();w.join(5)
    print('Device Fabric UI checks passed at 390/768/1440/3440: topology, indirect relay child, duplicate hint, blocked capability, Freebox authorization entry, relay pair/scan, guided relay error.')


if __name__=='__main__':main()
