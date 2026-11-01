"""UI V2 workspace smoke (hermetic): orb/comet behaviour from real events only, motion preferences, lifecycle,
keyboard, Studio rehearsal and Studio live path on fixtures, classic fallback, no horizontal overflow.

  python -m tests.e2e.ui_v2_smoke
"""
import json
import os
import threading
from playwright.sync_api import sync_playwright, expect
from src.server import create_server

SNAP = {'schema_version': 1, 'status': 'OK', 'providers': {},
        'devices': [{'key': 'dev-tv', 'category': 'tv', 'label': 'Living room TV', 'identifier_kinds': ['mdns'], 'facts': {}, 'capabilities': [], 'possibly_same_as': [], 'last_seen': '', 'handles': {}},
                    {'key': 'dev-watch', 'category': 'watch', 'label': 'Galaxy Watch', 'identifier_kinds': ['mdns'], 'facts': {}, 'capabilities': [], 'possibly_same_as': [], 'last_seen': '', 'handles': {}}],
        'links': [{'parent': 'pc', 'child': 'dev-tv', 'transport': 'WIFI', 'grants': ['observe', 'read', 'control'], 'source': 'test'},
                  {'parent': 'pc', 'child': 'dev-watch', 'transport': 'WIFI', 'grants': ['observe'], 'source': 'test'}],
        'possible_duplicates': []}
ROUTES = {'routes': [{'target_device': 'dev-watch', 'relay_device': 'dev-watch', 'relay_id': 'relay-w1', 'radio': 'ble', 'permission_granted': True, 'owner_enabled': True, 'online': True, 'last_success_at': None, 'status': 'FRESH'}]}
VIEWS = ['home', 'devices', 'network', 'capabilities', 'explore', 'studio', 'workflows', 'activity', 'settings', 'replay', 'advanced']


def debug(page):
    return page.evaluate('OBMotion.debug()')


def main():
    server = create_server(0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel=os.environ.get('OB_PLAYWRIGHT_CHANNEL') or None)

            # 1. First run at 1280x720: Ask above the fold, one orb, no comet without an event.
            ctx = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url + '#/home', wait_until='networkidle')
            box = page.locator('#ask-input').bounding_box()
            assert box and box['y'] + box['height'] <= 720, box
            expect(page.locator('#home-first-run')).to_be_visible()
            expect(page.locator('#home-stats')).to_be_hidden()
            page.wait_for_timeout(1500)
            d = debug(page)
            assert d['orbCanvases'] == 1 and d['flowCanvases'] == 1, d
            assert d['spawned'] == [0, 0] and d['comets'] == 0, d      # 0 events => 0 comets
            assert d['rafActive'] and d['orbFrames'] > 10, d          # orb visible + Full => animated
            nav = page.locator('nav.nav-v2 a span').all_inner_texts()
            assert nav[:5] == ['Home', 'Devices', 'Capabilities', 'Workflows', 'Activity'], nav
            expect(page.locator('#home-orb [data-orb-status] .orb-state')).to_have_text('Ready · waiting for your request')

            # 2. A real POST: OUT leaves the orb, the reply comes IN to the orb; amber/emerald constants.
            page.route('**/api/v2/command/tiers', lambda r: r.fulfill(json={'low': {'model': 'llama3.2', 'ready': True, 'estimate_usd': 0}, 'medium': {'ready': False}, 'high': {'configured': False, 'enabled': False}}))
            page.route('**/api/v2/command/parse', lambda r: r.fulfill(json={'intent': {'status': 'needs_clarification', 'clarifying_question': 'Which TV?'}}))
            page.reload(wait_until='networkidle')
            page.locator('#ask-input').fill('Turn the TV down')
            page.get_by_role('button', name='Ask', exact=True).click()
            expect(page.get_by_text('Which TV?')).to_be_visible()
            page.wait_for_function('() => OBMotion.debug().spawned[0] >= 1 && OBMotion.debug().spawned[1] >= 1')
            geo = page.evaluate("""() => { const g = OBMotion.orbGeometry(); const c = OBMotion.flow.comets.filter(x => x.alive || x.t > 0);
                return { g, flows: OBMotion.flow.comets.filter(x => x.label).map(x => ({ dir: x.dir, ax: x.ax, ay: x.ay, bx: x.bx, by: x.by, label: x.label, g: { x: x.orbX, y: x.orbY, r: x.orbR } })), cin: OBFlow.C_IN, cout: OBFlow.C_OUT }; }""")
            assert geo['cout'] == [255, 176, 64] and geo['cin'] == [52, 255, 170], geo
            for c in geo['flows']:
                g = c['g']
                start_d = ((c['ax'] - g['x']) ** 2 + (c['ay'] - g['y']) ** 2) ** .5
                end_d = ((c['bx'] - g['x']) ** 2 + (c['by'] - g['y']) ** 2) ** .5
                if c['dir'] == 1:
                    assert start_d < g['r'] * 1.1 < end_d, c         # OUT: orb -> away
                    assert c['label'].startswith('↑'), c
                else:
                    assert end_d < g['r'] * 1.1 < start_d, c         # IN: away -> orb
                    assert c['label'].startswith('↓'), c
            # a refused request: no IN comet, refusal text
            page.route('**/api/v2/command/parse', lambda r: r.fulfill(status=409, json={'error': 'model not ready'}))
            before = debug(page)['spawned'][0]
            page.get_by_role('button', name='Ask', exact=True).click()
            expect(page.locator('#home-orb .orb-state')).to_contain_text('Refused')
            page.wait_for_timeout(400)
            assert debug(page)['spawned'][0] == before
            page.unroute('**/api/v2/command/parse')

            # 3. Model settings collapsed; cloud consent only when needed.
            expect(page.get_by_text('AI quality')).to_be_hidden()
            assert page.locator('#ask-openbridge input[type=checkbox]').count() == 0

            # 4. Lifecycle: 100 navigations => one orb, one flow layer, one loop; hidden tab => no frames.
            for i in range(100):
                page.evaluate(f"location.hash = '#/{VIEWS[i % len(VIEWS)]}'")
            page.evaluate("location.hash = '#/devices'")
            page.wait_for_timeout(1800)
            d = debug(page)
            assert d['orbCanvases'] <= 1 and d['flowCanvases'] == 1, d   # the single orb canvas is detached, not duplicated
            assert not d['mounted'] and not d['rafActive'], d          # no orb, no comets => no frames
            page.evaluate("location.hash = '#/home'")
            page.wait_for_timeout(300)
            assert debug(page)['orbCanvases'] == 1
            page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))")
            f0 = debug(page)['frames']
            page.wait_for_timeout(600)
            assert debug(page)['frames'] == f0 and not debug(page)['rafActive']
            page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_timeout(300)
            assert debug(page)['rafActive']

            # 5. Keyboard: Ctrl+K palette, Esc closes, Alt+2 -> Devices.
            page.locator('#ask-input').focus()
            page.keyboard.press('Control+k')
            expect(page.locator('#palette')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('#palette')).to_be_hidden()
            assert page.evaluate("document.activeElement.id") == 'ask-input'
            page.keyboard.press('Alt+2')
            expect(page).to_have_url(url + '#/devices')

            # 6. Settings: Off stops the loop; the harness is labelled TEST.
            page.goto(url + '#/settings', wait_until='networkidle')
            page.locator('#settings-orb').scroll_into_view_if_needed()
            page.wait_for_function('() => OBMotion.debug().stageVisible')
            page.get_by_role('button', name='↑ OUT comet (amber)').click()
            expect(page.locator('#motion-test-banner')).to_be_visible()
            page.wait_for_function("() => OBMotion.flow.comets.some(c => c.alive && c.label.startsWith('TEST'))")
            page.get_by_role('button', name='thinking', exact=True).click()
            expect(page.locator('#settings-orb .orb-state')).to_contain_text('TEST')
            page.locator('label[for=set-motion-off]').click()
            page.wait_for_timeout(300)
            d = debug(page)
            assert d['motion'] == 'off' and not d['rafActive'] and d['comets'] == 0, d
            page.locator('label[for=set-motion-full]').click()
            assert not errors, errors
            ctx.close()

            # 7. prefers-reduced-motion: static orb, no loop, state text still present.
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
            page = ctx.new_page()
            page.goto(url + '#/home', wait_until='networkidle')
            page.wait_for_timeout(600)
            d = debug(page)
            assert d['motion'] == 'reduced' and not d['rafActive'] and d['orbFrames'] == 0, d
            expect(page.locator('#home-orb .orb-state')).to_have_text('Ready · waiting for your request')
            ctx.close()

            # 8. Studio rehearsal: SIMULATED everywhere, no runtime request.
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            hits = []
            page.route('**/api/v2/remote_controls**', lambda r: (hits.append(r.request.url), r.abort()))
            page.goto(url + '#/studio', wait_until='networkidle')
            page.get_by_role('button', name='Rehearse without hardware (SIMULATED)').click()
            expect(page.get_by_text('SIMULATED REHEARSAL')).to_be_visible()
            page.get_by_role('button', name='Find devices & propose').click()
            expect(page.get_by_text('PREVIEW ONLY — nothing installed')).to_be_visible()
            expect(page.locator('.watch-btn')).to_have_count(2)
            assert page.locator('#studio-install').is_disabled()
            page.locator('label[for=studio-consent]').click()
            page.locator('#studio-install').click()
            expect(page.get_by_text('SIMULATED · installed on a simulated watch')).to_be_visible()
            assert 'null' not in page.locator('#studio-root').inner_text()
            assert page.evaluate('() => OBMotion.debug().spawned[1]') >= 1      # SIM-labelled OUT toward the watch preview
            page.get_by_role('button', name='Run “Volume +” from this PC').click()
            page.get_by_role('button', name='Run once').click()
            expect(page.get_by_text('Volume +: Sent · effect not verified')).to_be_visible()
            page.get_by_role('button', name='Revoke these controls').click()
            expect(page.get_by_text('REVOKED · drawn controls no longer run')).to_be_visible()
            assert hits == [], hits
            assert not errors, errors
            ctx.close()

            # 9. Studio live path on fixtures: owner path with consent, ACK is not a physical effect, revoke.
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = ctx.new_page()
            sent = []
            page.route('**/api/fabric', lambda r: r.fulfill(json=SNAP))
            page.route('**/api/v2/routes', lambda r: r.fulfill(json=ROUTES))

            def controls(r):
                if r.request.method != 'POST':
                    return r.fulfill(json={'controls': []})
                body = r.request.post_data_json
                sent.append(body)
                out = [{'relay_id': body['relay_id'], 'control_id': f'ctl-{i}-g1', 'label': c['label'], 'skill_id': c['skill_id']} for i, c in enumerate(body['controls'])]
                r.fulfill(json={'controls': out, 'layouts': {}, 'history': []})
            page.route('**/api/v2/remote_controls', controls)
            page.route('**/api/v2/remote_controls/invoke', lambda r: r.fulfill(json={'control_id': 'ctl-1-g1', 'state': 'EXECUTED', 'reason': 'Volume +: done', 'transaction_id': 'tx-1'}))
            page.goto(url + '#/studio', wait_until='networkidle')
            page.get_by_role('button', name='Find devices & propose').click()
            expect(page.locator('#studio-source')).to_have_value('dev-tv')
            expect(page.locator('#studio-target')).to_have_value('relay-w1')
            expect(page.locator('.checks li.bad')).to_have_count(0)
            page.locator('label[for=studio-consent]').click()
            page.locator('#studio-install').click()
            expect(page.get_by_text('INSTALLED · acknowledged by the Companion')).to_be_visible()
            expect(page.get_by_text('This is not a physical effect yet.', exact=False)).to_be_visible()
            assert sent[0]['consent'] is True and sent[0]['relay_id'] == 'relay-w1', sent
            assert [c['params'] for c in sent[0]['controls']] == [{'direction': 'down'}, {'direction': 'up'}], sent
            assert all(c['skill_id'] == 'tv_volume_step' and c['target'] == 'dev-tv' for c in sent[0]['controls'])
            page.get_by_role('button', name='Run “Volume +” from this PC').click()
            page.get_by_role('button', name='Run once').click()
            expect(page.get_by_text('Volume +: Sent · effect not verified')).to_be_visible()
            page.get_by_role('button', name='Revoke these controls').click()
            expect(page.get_by_text('Revoked. New presses are refused by this PC.')).to_be_visible()
            assert sent[-1] == {'relay_id': 'relay-w1', 'controls': [], 'consent': True}, sent[-1]
            ctx.close()

            # 10. Classic fallback and responsive overflow.
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = ctx.new_page()
            page.goto(url + '?ui=classic#/home', wait_until='networkidle')
            expect(page.locator('nav.nav-classic')).to_be_visible()
            expect(page.locator('nav.nav-v2')).to_be_hidden()
            ctx.close()
            for w, h in ((390, 844), (768, 1024), (1440, 900), (3440, 1440)):
                ctx = browser.new_context(viewport={'width': w, 'height': h})
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                for v in VIEWS:
                    page.goto(url + '#/' + v, wait_until='networkidle')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (v, w)
                assert not errors, (w, errors)
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('UI V2 workspace passed: real-event comets (IN/OUT direction + colours), refusal, lifecycle (100 navigations, hidden tab), '
          'motion Full/Reduced/Off + harness, keyboard, Studio rehearsal + live fixtures, classic fallback, 390–3440 px.')


if __name__ == '__main__':
    main()
