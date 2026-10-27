"""Real source-selection HTTP and browser lifecycle with controlled runtime facts only."""
import copy
import threading
from playwright.sync_api import sync_playwright, expect
from src.forge.workspace import WorkspaceManager, create_workspace_server
from tests.forge.test_workspace import runtime_data


def main():
    data = runtime_data()
    manager = WorkspaceManager(lambda path: copy.deepcopy(data[path]), allow_simulated=True)
    server = create_workspace_server(0, manager)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (390, 768, 1440, 3440):
                page = browser.new_page(viewport={'width': width, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base, wait_until='networkidle')
                expect(page.locator('#route-status')).to_have_text('No route check has run.')
                page.get_by_role('button', name='Refresh verified routes').click()
                expect(page.locator('#route-status')).to_contain_text('1 verified route')
                expect(page.locator('#routes')).to_contain_text('SIMULATED / CONTROLLED DATA')
                page.get_by_role('button', name='Create bound workspace').click()
                link = page.get_by_role('link', name='Open SIMULATED bound workspace')
                expect(link).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                link.click()
                expect(page.locator('#source-mode')).to_contain_text('SIMULATED')
                page.select_option('#planner', 'rules')
                page.get_by_role('button', name='Find a safe path').click()
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                assert page.locator('#publish').is_disabled()
                page.locator('#consent').check()
                page.get_by_role('button', name='Build local service').click()
                expect(page.locator('#operation')).to_contain_text('First observation read verified')
                page.get_by_role('button', name='Test the local service').click()
                expect(page.locator('#output')).to_contain_text('rssi_dbm')
                page.get_by_role('button', name='Stop & remove service').click()
                expect(page.locator('#operation')).to_contain_text('Stopped and removed')
                page.goto(base, wait_until='networkidle')
                page.get_by_role('button', name='Close workspace and remove services').click()
                expect(page.locator('#session-status')).to_contain_text('Workspace closed')
                assert not manager.sessions()
                data['/api/v2/routes']['routes'][0]['online'] = False
                page.get_by_role('button', name='Refresh verified routes').click()
                expect(page.locator('#route-status')).to_contain_text('No eligible current observations')
                assert page.get_by_role('button', name='Create bound workspace').count() == 0
                data['/api/v2/routes']['routes'][0]['online'] = True
                page.keyboard.press('Tab')
                assert page.evaluate('document.activeElement.tagName') != 'BODY'
                assert not errors, errors
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    print('Source selection, bound publication/read/removal, offline refusal and cleanup passed at four widths; no model/device calls.')


if __name__ == '__main__':
    main()
