from pathlib import Path
import threading
from playwright.sync_api import sync_playwright
from src.server import create_server
from src.forge.demo_host import create_forge_server
servers=[create_server(0),create_forge_server(0)]
for server in servers:threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True)
  for name,server in zip(['main','forge'],servers):
   for width in [390,768,1440,3440]:
    page=b.new_page(viewport={'width':width,'height':1050});page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
    path=Path('artifacts/web-redesign')/f'{name}-{width}.png';path.parent.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(path),full_page=True);page.close()
  b.close()
finally:
 for server in servers:server.shutdown();server.server_close()
print('Eight responsive screenshots captured; no horizontal overflow.')
