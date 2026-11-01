"""Ask OpenBridge panel: English UI under French locale, tier pills, fixtures-only ask flow."""
import os
import re
import threading
from playwright.sync_api import sync_playwright, expect
from src.server import create_server

TIERS = {'low': {'model': 'llama3.2:3b-instruct-q4_K_M', 'endpoint': 'http://127.0.0.1:11437',
                 'ready': True, 'estimate_usd': 0.0},
         'medium': {'model': 'muse-glimmer:30b-q4_K_M', 'endpoint': 'http://127.0.0.1:11438',
                    'ready': False, 'estimate_usd': 0.0},
         'high': {'model': 'muse-spark-1.3', 'endpoint': 'https://api.meta.ai/v1/chat/completions',
                  'configured': False, 'enabled': True, 'estimate_usd': 0.10}}
INTENT = {'intent_id': 'int-smoke1', 'version': 1, 'raw_text': 'Scan for bluetooth devices',
          'lang': 'en', 'outcome': 'scan nearby', 'targets': [{'kind': 'device', 'ref': 'tv'}],
          'skill_id': 'ble_scan_room', 'params': {}, 'confidence': 1.0, 'ambiguities': [],
          'clarifying_question': None, 'risk_level': 'low', 'status': 'resolved',
          'provenance': {'parser': 'local', 'model_id': 'llama3.2:3b-instruct-q4_K_M'}}
PREVIEW = {'skill_id': 'ble_scan_room', 'primitive_id': 'b2:ble_scan_room', 'params': {},
           'device_keys': ['dev-tv1'],
           'approved_targets': [{'key': 'dev-tv1', 'label': 'TV', 'category': 'tv'}],
           'risk_level': 'low', 'verification': 'claimed', 'consent_required': True,
           'route': {'selected_route_id': 'rt-1', 'rule': 'auto_score', 'states': []},
           'fingerprint': 'f' * 64}


def main():
    server = create_server(0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as p:
            channel = os.environ.get('OB_PLAYWRIGHT_CHANNEL') or None
            browser = p.chromium.launch(headless=True, channel=channel)
            for width in (390, 1440):
                ctx = browser.new_context(viewport={'width': width, 'height': 1000}, locale='fr-FR')
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                seen = {}
                page.route('**/api/v2/command/tiers',
                           lambda r: r.fulfill(status=200, json=TIERS))
                page.route('**/api/v2/command/parse',
                           lambda r: r.fulfill(status=200, json={'intent': INTENT, 'cloud_used': False,
                                                                 'estimate_usd': 0.0}))
                page.route('**/api/v2/command/approve',
                           lambda r: r.fulfill(status=200, json=PREVIEW))
                page.route('**/api/v2/companion/commands*',
                           lambda r: r.fulfill(status=200, json={'pending': [
                               {'request_id': 'c' * 32, 'relay_id': 'r-phone',
                                'text': 'Start my vacuum', 'lang': 'en', 'intent': dict(
                                    INTENT, skill_id='vacuum.start', outcome='start cleaning')}]}))

                def on_execute(r):
                    seen['execute'] = r.request.post_data_json
                    r.fulfill(status=200, json={'state': 'VERIFIED', 'transaction_id': 'tx-smoke-1'})
                page.route('**/api/v2/command/execute', on_execute)
                page.goto(f'http://127.0.0.1:{server.server_port}/#/home', wait_until='networkidle')
                panel = page.locator('#ask-openbridge')
                expect(panel).to_be_visible()
                # V2.1: one compact AI-quality choice; free (local) vs paid (cloud) is explicit on each option.
                expect(panel.get_by_text('AI quality')).to_be_visible()
                expect(panel.locator('.ask-tier .tier-cost.free')).to_have_count(3)
                expect(panel.locator('.ask-tier .tier-cost.paid')).to_have_count(1)
                assert panel.get_by_role('checkbox').count() == 0, 'cloud consent must not show before it is needed'
                panel.get_by_role('radio', name=re.compile('^Pro')).click()
                expect(panel.get_by_role('checkbox')).to_be_visible()      # shown only once the paid cloud tier is chosen
                panel.get_by_role('radio', name=re.compile('^Auto')).click()
                expect(panel.get_by_role('checkbox')).to_have_count(0)
                body = panel.inner_text()
                assert 'Envoyer' not in body and 'Qualité' not in body, 'UI must stay English'
                assert 'llama3.2' in body and '~$0.10' in body
                panel.get_by_role('button', name='Check devices').click()
                expect(panel.get_by_text('Start my vacuum').first).to_be_visible()
                expect(panel.get_by_text('resolved · vacuum.start')).to_be_visible()
                panel.get_by_role('button', name='Load').click()
                expect(page.locator('#ask-input')).to_have_value('Start my vacuum')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if width == 1440:
                    page.locator('#ask-input').fill('Scan for bluetooth devices')
                    panel.get_by_role('button', name='Ask', exact=True).click()
                    expect(panel.get_by_text('Understanding request')).to_be_visible()
                    approve = panel.get_by_role('button', name='Approve & execute')
                    expect(approve).to_be_visible(timeout=15000)
                    expect(panel.get_by_text('ble_scan_room')).to_be_visible()
                    approve.click()
                    expect(panel.get_by_text('tx-smoke-1')).to_be_visible(timeout=15000)
                    assert seen['execute']['preview']['fingerprint'] == 'f' * 64
                    assert seen['execute']['consent'] is True
                assert not errors, errors
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print('Command Center English UI, tiers, fixtures-only ask/approve/execute passed at 390/1440.')


if __name__ == '__main__':
    main()
