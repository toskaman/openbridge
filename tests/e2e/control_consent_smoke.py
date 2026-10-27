"""Controlled consent regressions for actual UI panel functions; no server/device/model calls."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'src/ui/app.js').read_text(encoding='utf-8')
HELPER = SOURCE[SOURCE.index('function element('):SOURCE.index('\n}', SOURCE.index('function element(')) + 2]
PANELS = SOURCE[SOURCE.index('function tuyaPanel('):]


def mount(page, kind):
    page.set_content('<main></main>')
    page.evaluate("() => {" + HELPER + PANELS + """
      window.calls = [];
      window.waitForReply = false;
      window.postJson = async (path, body) => {
        calls.push(body);
        if (waitForReply) await new Promise(resolve => { window.reply = resolve; });
        return {state:'VERIFIED', verified:true, before:1, after:2, errors:[], result:{exit_code:0}};
      };
      document.querySelector('main').append(""" + kind + "Panel({key:'fixture-device'}));}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in (390, 768, 1440, 3440):
            page = browser.new_page(viewport={'width':width,'height':1000})
            mount(page, 'job')
            page.locator('textarea').fill('hostname')
            page.get_by_role('checkbox').check()
            page.locator('select').select_option('cmd')
            expect(page.get_by_role('checkbox')).not_to_be_checked()
            page.get_by_role('button', name='Run on this PC', exact=True).click()
            assert page.evaluate('calls.length') == 0
            page.get_by_role('checkbox').check()
            page.evaluate('window.waitForReply = true')
            page.get_by_role('button', name='Run on this PC', exact=True).click()
            expect(page.get_by_role('checkbox')).not_to_be_checked()
            expect(page.locator('textarea')).to_be_disabled()
            expect(page.locator('select')).to_be_disabled()
            page.evaluate('window.reply()')
            expect(page.locator('textarea')).to_be_enabled()
            assert page.evaluate('calls[0].params') == {'command':'hostname','shell':'cmd','timeout_s':120}
            mount(page, 'tuya')
            page.get_by_role('checkbox').check()
            page.get_by_role('button', name='Change with read-back', exact=True).click()
            expect(page.get_by_role('button', name='Undo exactly', exact=True)).to_be_visible()
            expect(page.get_by_role('checkbox')).not_to_be_checked()
            page.locator('select').first.select_option('volume')
            page.get_by_role('button', name='Undo exactly', exact=True).click()
            assert page.evaluate('calls[1].params.setting') == 'suction'
            page.get_by_role('button', name='Start', exact=True).click()
            assert page.evaluate('calls.length') == 2
            page.get_by_role('checkbox').check()
            page.get_by_role('button', name='Start', exact=True).click()
            expect(page.get_by_role('checkbox')).not_to_be_checked()
            assert page.evaluate('calls.length') == 3
            mount(page, 'remote')
            page.get_by_role('checkbox').check()
            page.get_by_role('button', name='Set volume (exact undo)', exact=True).click()
            assert page.evaluate('calls.length') == 0, 'Blank volume must not become a zero-volume command'
            page.locator('input[type=number]').fill('3.5')
            page.get_by_role('button', name='Set volume (exact undo)', exact=True).click()
            assert page.evaluate('calls.length') == 0, 'Fractional volume must not be silently truncated'
            page.locator('input[type=number]').fill('0')
            page.get_by_role('button', name='Set volume (exact undo)', exact=True).click()
            assert page.evaluate('calls[0].params.args.value') == 0
            page.get_by_role('button', name='Launch', exact=True).click()
            assert page.evaluate('calls.length') == 1, 'No empty package launch'
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.get_by_role('button', name='Load apps', exact=True).click()
            expect(page.get_by_role('status')).to_contain_text('No launchable apps')
            assert not errors, errors
            page.close()
        browser.close()
    print('Exact job consent, in-flight locking and robot Undo binding passed at four widths; zero device/model calls.')


if __name__ == '__main__':
    main()
