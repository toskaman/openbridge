"""Mocked browser-only model UI verification; never calls a provider."""
import json
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.route('**/api/model-status',lambda route:route.fulfill(json={'supervised_session_configured':True}))
        captured=[]
        page.route('**/api/recommend',lambda route:captured.append(route))
        page.goto('http://127.0.0.1:18765',wait_until='networkidle')
        button=page.get_by_role('button',name='Request Meta advice')
        assert button.is_enabled()
        button.click()
        page.get_by_text('Requesting Meta Muse Spark 1.3 advice',exact=False).wait_for()
        page.get_by_role('radio',name='Android USB').check()
        page.get_by_role('radio',name='Simulated demo').check()
        assert button.is_disabled(), 'Source changes must not enable a second pending model request'
        assert len(captured)==1
        assert json.loads(captured[0].request.post_data)['source']=='demo'
        captured[0].fulfill(json={'model_id':'muse-spark-1.3','proposal':{'summary':'MOCKED_STALE_RESULT','evidence_refs':['battery_percent'],'uncertainty':'synthetic'},'estimated_cost_usd':0.001})
        expect(button).to_be_enabled()
        assert 'MOCKED_STALE_RESULT' not in page.locator('#meta-result').inner_text()
        page.unroute('**/api/recommend')
        page.route('**/api/recommend',lambda route:route.fulfill(status=409,json={'error':'Credit observation expired'}))
        button.click()
        page.get_by_text('Meta request blocked or failed:',exact=False).wait_for()
        assert 'Credit observation expired' in page.locator('#meta-result').inner_text()
        browser.close()
    print('Mocked Meta UI passed: one pending call, stale response discarded, expired credits explained; zero provider calls.')


if __name__=='__main__':
    main()
