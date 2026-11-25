"""OpenAPI spec: complete coverage (anti-rot), committed file in sync, sane shapes."""
import json
import unittest
from pathlib import Path

from src.runtime import api_v2
from src.runtime import openapi as O

ROOT = Path(__file__).resolve().parent.parent.parent
COMMITTED = ROOT / 'docs' / 'api' / 'openapi.json'


class Spec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = O.build()

    def test_every_route_covered(self):
        paths = self.spec['paths']
        for route in api_v2.GET_ROUTES:
            self.assertIn('get', paths.get(route, {}), route)
        for route in api_v2.POST_ROUTES:
            self.assertIn('post', paths.get(route, {}), route)
        self.assertEqual(set(paths), set(api_v2.GET_ROUTES) | set(api_v2.POST_ROUTES))

    def test_shape(self):
        self.assertTrue(self.spec['openapi'].startswith('3.0.'))
        self.assertIn('info', self.spec)
        ids = set()
        for path, item in self.spec['paths'].items():
            for method, op in item.items():
                self.assertIn('operationId', op, path)
                self.assertIn('responses', op, path)
                self.assertIn('200', op['responses'], path)
                self.assertNotIn(op['operationId'], ids)
                ids.add(op['operationId'])
                if method == 'post':
                    self.assertIn('requestBody', op, path)

    def test_curated_shapes(self):
        lib = self.spec['paths']['/api/v2/library/approve']['post']['requestBody']['content']
        self.assertEqual(lib['application/json']['schema']['required'], ['id', 'consent'])
        exe = self.spec['paths']['/api/v2/execute']['post']['requestBody']['content']
        self.assertIn('primitive_id', exe['application/json']['schema']['properties'])

    def test_committed_file_in_sync(self):
        self.assertTrue(COMMITTED.exists(), 'run: python -m src.runtime.openapi')
        disk = json.loads(COMMITTED.read_text(encoding='utf-8'))
        self.assertEqual(disk, json.loads(json.dumps(self.spec)))


if __name__ == '__main__':
    unittest.main()
