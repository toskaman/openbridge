"""Injected simulated providers must not inherit the default fixture's invented device names."""
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.fixtures import manifest
from src.forge.service import MemoryProvider
from src.forge.demo_host import create_forge_server

def main():
 m=manifest();m.update(relay_id='phone-fixture',source='RELAY:phone-fixture',capability_id='phone.observations',service_id='phone-signals')
 server=create_forge_server(0,provider=MemoryProvider(m),capability_id=m['capability_id']);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True);page=b.new_page();page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
   expect(page.locator('#relay-title')).to_have_text('Fixture relay')
   expect(page.locator('#source-pill')).to_have_text('SIMULATED FIXTURE')
   expect(page.locator('#twin-identity')).to_contain_text('phone-fixture')
   assert page.locator('#refresh-fixture').is_hidden();b.close()
 finally:server.shutdown();server.server_close();t.join()
 print('Injected simulated source labels passed; default TV identity not inherited.')
if __name__=='__main__':main()
