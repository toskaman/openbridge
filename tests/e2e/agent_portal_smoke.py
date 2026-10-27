"""Headless onboarding checks against a mocked daemon; no device or model calls."""
import hashlib
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dev import agent_portal
from playwright.sync_api import expect, sync_playwright


def main():
    # Replace the daemon boundary before starting the real portal HTTP server.
    state = {'connected': False, 'command': 'agent.exe --host 192.168.1.2 --port 9876 --token TEST_ONLY'}
    agent_portal.daemon_state = lambda: dict(state)
    payload = b'mocked executable; never run'
    server = agent_portal.Portal(('127.0.0.1', 0), agent_portal.build_handler(
        '192.168.1.2', payload, hashlib.sha256(payload).hexdigest(), len(payload)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (390, 768, 1440, 3440):
                context = browser.new_context(viewport={'width': width, 'height': 1000},
                                              permissions=['clipboard-read', 'clipboard-write'])
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                state.clear()
                state.update(connected=False, command='agent.exe --host 192.168.1.2 --port 9876 --token TEST_ONLY')
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                assert page.locator('html').get_attribute('lang') == 'en'
                expect(page.get_by_role('heading', name='Connect this PC to OpenBridge')).to_be_visible()
                expect(page.locator('#state')).to_have_text('Waiting for the PC…')
                expect(page.locator('#cmd')).to_have_text(state['command'])
                page.get_by_role('button', name='Copy', exact=True).click()
                expect(page.locator('#copy')).to_have_text('Copied ✓')
                assert page.evaluate('navigator.clipboard.readText()') == state['command']
                page.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('clipboard denied')); }")
                page.locator('#copy').click()
                expect(page.locator('#copy')).to_have_text('Select and copy')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                state.update(connected=True, arch='x64', version='1.2.3', metrics={
                    'cpu': 18, 'cores': 8, 'ram_used_pct': 40, 'disk_free_gb': 256,
                    'uptime_h': 2, 'rtt_ms': 12})
                page.evaluate('poll()')
                expect(page.locator('#state')).to_have_text('Connected ✓')
                expect(page.locator('#metrics')).to_be_visible()
                expect(page.locator('#m-disk')).to_have_text('256 GB')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                state.clear()
                state.update(connected=False, command=None)
                page.reload()
                expect(page.locator('#cmd')).to_contain_text('<YOUR_KEY>')
                expect(page.locator('#metrics')).to_be_hidden()
                page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
                page.locator('#copy').click()
                expect(page.locator('#copy')).to_have_text('Copied ✓')
                page.route('**/api/state', lambda route: route.abort())
                page.evaluate('poll()')
                expect(page.locator('#state')).to_have_text('Portal active')
                expect(page.locator('#statesub')).to_have_text('Start the OpenBridge service to see live status.')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('Portal waiting, connected, unavailable and copy checks passed at 390/768/1440/3440.')


if __name__ == '__main__':
    main()
