"""Real-network Device Fabric UI check (not CI): requires a server on 127.0.0.1:18799. Read-only discovery only."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def main():
    out=Path('artifacts/fabric');out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True);first=True
        for width in (390,768,1440,3440):
            page=b.new_page(viewport={'width':width,'height':1000});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:18799',wait_until='networkidle')
            if first:
                page.get_by_role('button',name='Discover my environment').click();first=False
            expect(page.locator('#fabric-meta')).to_contain_text('DEVICE(S)',timeout=60000)
            nodes=page.locator('#fabric-tree .fabric-node')
            if nodes.count()>1:nodes.nth(1).click()
            page.locator('#fabric').screenshot(path=str(out/f'{width}-fabric.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'overflow'
            assert not errors,errors
            print(width,page.locator('#fabric-meta').inner_text(),'|',page.locator('#fabric-providers').inner_text().replace('\n',' | '))
            page.close()
        b.close()

if __name__=='__main__':main()
