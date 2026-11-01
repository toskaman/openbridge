"""UI V2 workspace: static contracts that keep the web orb/comets faithful to the Android Companion and the
new assets wired, served and side-effect free. Browser behaviour is covered by tests/e2e/ui_v2_smoke.py."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / 'src' / 'ui'
JAVA = ROOT / 'companion' / 'android' / 'src' / 'fr' / 'openbridge' / 'companion'
MOTION = ['motion/orb_canvas.js', 'motion/flow_canvas.js', 'motion/motion_controller.js', 'motion/motion_state.js']
VIEWS = ['views/studio_view.js', 'views/settings_view.js', 'views/workflows_view.js']


def text(path):
    return Path(path).read_text(encoding='utf-8')


class OrbParityWithCompanion(unittest.TestCase):
    def test_palette_matches_voice_orb_view(self):
        java = text(JAVA / 'VoiceOrbView.java')
        rows = re.findall(r'\{Color\.rgb\((\d+), (\d+), (\d+)\), Color\.rgb\((\d+), (\d+), (\d+)\), Color\.rgb\((\d+), (\d+), (\d+)\)\}', java)
        self.assertEqual(len(rows), 6)
        expected = [[[int(r[i]), int(r[i + 1]), int(r[i + 2])] for i in (0, 3, 6)] for r in rows]
        js = text(UI / 'motion/orb_canvas.js')
        block = js[js.index('const PALETTE = ['):js.index('];', js.index('const PALETTE = ['))]
        got = json.loads('[' + re.sub(r'//[^\n]*', '', block.split('[', 1)[1]).strip().rstrip(',') + ']')
        self.assertEqual(got, expected)

    def test_sphere_sampling_and_states(self):
        java = text(JAVA / 'VoiceOrbView.java')
        js = text(UI / 'motion/orb_canvas.js')
        lat, lon = re.search(r'LAT = (\d+), LON = (\d+)', java).groups()
        self.assertIn(f'const LAT = {lat}, LON = {lon}', js)
        self.assertEqual(int(lat) * int(lon), 828)
        for state in ('IDLE', 'LISTENING', 'THINKING', 'SPEAKING', 'ALERT', 'OFFLINE'):
            self.assertIn(state, java)
            self.assertIn(f"'{state}'", js)
        # Same noise, projection and ribbon constants as the Companion.
        for const in ('focal = 3.2', '0.035 + 0.26', '18.85', '25.1', '37.7', 'R * 1.55', '1.6 + r * 0.55', 'R * 1.22', 'R * 1.32'):
            self.assertIn(const, js)

    def test_flow_colours_limits_and_direction(self):
        java = text(JAVA / 'FlowOverlayView.java')
        js = text(UI / 'motion/flow_canvas.js')
        out = re.search(r'C_OUT = Color\.rgb\((\d+), (\d+), (\d+)\)', java).groups()
        inn = re.search(r'C_IN = Color\.rgb\((\d+), (\d+), (\d+)\)', java).groups()
        self.assertIn('C_OUT = [%s, %s, %s]' % out, js)
        self.assertIn('C_IN = [%s, %s, %s]' % inn, js)
        mx, trail = re.search(r'MAX = (\d+), TRAIL = (\d+)', java).groups()
        self.assertIn(f'MAX = {mx}, TRAIL = {trail}', js)
        self.assertIn('QUEUE_MAX = 256', js)
        self.assertIn('LABELS_MAX = 8', js)
        self.assertIn('label.length > 26', js)
        # OUT leaves the orb (a = orb edge), IN arrives at the orb (b = orb edge).
        self.assertIn('if (dir === OUT) { c.ax = sx; c.ay = sy; c.bx = ox; c.by = oy; } else { c.ax = ox; c.ay = oy; c.bx = sx; c.by = sy; }', js)


class MotionIsVisualOnly(unittest.TestCase):
    def test_renderers_never_fetch_or_poll(self):
        for name in MOTION:
            src = text(UI / name)
            self.assertIsNone(re.search(r'setInterval\s*\(', src), name)
        for name in ('motion/orb_canvas.js', 'motion/flow_canvas.js', 'motion/motion_controller.js'):
            src = text(UI / name)
            self.assertIsNone(re.search(r'\bfetch\s*\(', src), name)
            self.assertNotIn('XMLHttpRequest', src, name)
            self.assertNotIn('postJson', src, name)

    def test_single_loop_and_lifecycle_hooks(self):
        src = text(UI / 'motion/motion_controller.js')
        self.assertEqual(src.count('requestAnimationFrame('), 1)
        for hook in ('visibilitychange', 'IntersectionObserver', 'ResizeObserver', 'cancelAnimationFrame', 'prefers-reduced-motion', 'ob-flow-layer'):
            self.assertIn(hook, src)
        css = text(UI / 'theme/workspace_v2.css')
        self.assertRegex(css, r'\.ob-flow-layer\{[^}]*pointer-events:none')
        self.assertRegex(css, r'\.ob-orb-canvas\{[^}]*pointer-events:none')

    def test_test_and_replay_sources_are_labelled(self):
        src = text(UI / 'motion/motion_controller.js')
        self.assertIn("origin === 'test' ? 'TEST'", src)
        self.assertIn("'REPLAY'", src)
        self.assertIn("'SIM'", src)
        self.assertIn('TEST HARNESS', text(UI / 'index.html'))

    def test_adapter_maps_only_real_sources(self):
        src = text(UI / 'motion/motion_state.js')
        self.assertIn("method !== 'POST'", src)
        self.assertIn("if (!primed) { primed = true; return; }", src)   # history never animates
        self.assertIn("r.status === 403", src)
        self.assertNotIn('Math.random', src)


class AssetsServedAndWired(unittest.TestCase):
    def test_assets_registered_and_loaded_in_order(self):
        server = text(ROOT / 'src/server.py')
        index = text(UI / 'index.html')
        for name in MOTION + VIEWS:
            self.assertTrue((UI / name).is_file(), name)
            self.assertIn(f"'/{name}': ('{name}', 'text/javascript')", server)
            self.assertIn(f'<script defer src="/{name}"></script>', index)
        self.assertLess(index.index('/motion/motion_state.js'), index.index('/app.js'))
        self.assertLess(index.index('/views/studio_view.js'), index.index('/shell.js'))

    def test_assets_answer_over_http(self):
        import threading
        import urllib.request
        from src.server import create_server
        server = create_server(0)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            for name in MOTION + VIEWS:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/{name}', timeout=5) as r:
                    self.assertEqual(r.status, 200)
                    self.assertEqual(r.headers['Content-Type'], 'text/javascript')
                    self.assertIn("script-src 'self'", r.headers['Content-Security-Policy'])
        finally:
            server.shutdown()
            server.server_close()

    def test_theme_source_compiled(self):
        self.assertIn("'workspace_v2.css'", text(ROOT / 'dev/build_web_theme.py'))
        css = text(UI / 'style.css')
        self.assertIn('/* workspace_v2.css */', css)
        self.assertIn('--v2-in:#34FFAA', css)
        self.assertIn('--v2-out:#FFB040', css)

    def test_five_primary_sections_and_legacy_routes(self):
        index = text(UI / 'index.html')
        nav = index[index.index('<nav class="nav nav-v2"'):index.index('</nav>', index.index('<nav class="nav nav-v2"'))]
        self.assertEqual(re.findall(r'<span>([^<]+)</span>', nav), ['Home', 'Devices', 'Capabilities', 'Workflows', 'Activity'])
        self.assertEqual(index.count('id="ask-nav"'), 1)
        shell = text(UI / 'shell.js')
        for legacy in ('skills', 'fabric', 'automations', 'explore', 'advanced', 'replay'):
            self.assertRegex(shell, r"\b%s: '" % legacy)
        self.assertIn("ui=classic", shell)
        for view in ('studio', 'settings'):
            self.assertIn(f'data-view="{view}"', index)


class StudioHonesty(unittest.TestCase):
    def test_install_and_revoke_use_owner_path_with_consent(self):
        src = text(UI / 'views/studio_view.js')
        self.assertIn("post('/api/v2/remote_controls', { relay_id: S.relay, controls, consent: true })", src)
        self.assertIn("post('/api/v2/remote_controls', { relay_id: S.relay, controls: [], consent: true })", src)
        self.assertIn("post('/api/v2/remote_controls/invoke', { relay_id: S.relay, control_id: c.control_id, consent: true })", src)
        self.assertIn('PREVIEW ONLY — nothing installed', src)
        self.assertIn('not a physical effect', src)
        self.assertIn("'Sent · effect not verified'", src)
        self.assertNotIn('confirm(', src.replace('ask(', '').replace("'Confirm'", '').replace('Confirm', ''))

    def test_rehearsal_never_reaches_the_runtime(self):
        src = text(UI / 'views/studio_view.js')
        for fn in ('async function install()', 'async function runFromPc(c)', 'async function revoke()'):
            body = src[src.index(fn):src.index('\n  }\n', src.index(fn))]
            start = body.index('if (S.sim)')
            sim = body[start:body.index('else', start)]
            self.assertNotIn('post(', sim, fn)
        self.assertIn('SIMULATED REHEARSAL', src)


if __name__ == '__main__':
    unittest.main()
