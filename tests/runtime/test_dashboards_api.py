"""§8 dashboards API (SIMULATED_VERIFIED: FakeCompanion, tmp journal)."""
import tempfile
import unittest

from src.fabric.session import SessionJournal
from src.runtime.api_v2 import get, post
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock, world


class DashboardsApi(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-ph-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.server.session_journal = SessionJournal(tempfile.mkdtemp() + '/s.json')

    def test_create_patch_save_load_flow(self):
        code, _ = post(self.server, '/api/v2/dashboards/create',
                       {'relay_id': 'r-watch', 'area': 'vacuum',
                        'target': 'vacuum-key', 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(len(self.companion.controls), 4)
        code, _ = post(self.server, '/api/v2/dashboards/patch',
                       {'relay_id': 'r-watch', 'remove': ['Find me'], 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(len(self.companion.controls), 3)
        code, body = post(self.server, '/api/v2/dashboards/save',
                          {'relay_id': 'r-watch', 'name': 'evening'})
        self.assertEqual((code, body['saved']), (200, 'evening'))
        code, body = get(self.server, '/api/v2/dashboards/list', '')
        self.assertEqual(body['dashboards'], ['evening'])
        code, _ = post(self.server, '/api/v2/dashboards/create',
                       {'relay_id': 'r-watch', 'area': 'tv', 'target': 'tv-key',
                        'consent': True})
        self.assertEqual(len(self.companion.controls), 3)
        code, _ = post(self.server, '/api/v2/dashboards/load',
                       {'name': 'evening', 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(len(self.companion.controls), 3)
        code, body = post(self.server, '/api/v2/dashboards/delete', {'name': 'evening'})
        self.assertEqual((code, body['deleted']), (200, 'evening'))

    def test_create_rejects_unknown_area(self):
        code, body = post(self.server, '/api/v2/dashboards/create',
                          {'relay_id': 'r-watch', 'area': 'toaster',
                           'target': 'x', 'consent': True})
        self.assertEqual(code, 400)

    def test_patch_remove_unknown_is_400(self):
        post(self.server, '/api/v2/dashboards/create',
             {'relay_id': 'r-watch', 'area': 'vacuum', 'target': 'vacuum-key',
              'consent': True})
        code, _ = post(self.server, '/api/v2/dashboards/patch',
                       {'relay_id': 'r-watch', 'remove': ['Nope'], 'consent': True})
        self.assertEqual(code, 400)

    def test_restore_flow(self):
        post(self.server, '/api/v2/dashboards/create',
             {'relay_id': 'r-watch', 'area': 'vacuum', 'target': 'vacuum-key',
              'consent': True})
        post(self.server, '/api/v2/dashboards/save',
             {'relay_id': 'r-watch', 'name': 'evening'})
        code, body = post(self.server, '/api/v2/dashboards/restore', {'relay_id': 'r-watch'})
        self.assertEqual((code, body['restored']), (200, None))


if __name__ == '__main__':
    unittest.main()
