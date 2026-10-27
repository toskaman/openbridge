import unittest
from src.runtime import preflight as p


class Preflight(unittest.TestCase):
    def test_model_digest_pinning(self):
        def fetch(url):
            if ':11437' in url:
                return {'models': [{'name': 'llama3.2:3b-instruct-q4_K_M', 'digest': p.MODELS[11437][1]}]}
            return {'models': [{'name': 'muse-glimmer:30b-q4_K_M', 'digest': '00000000'}]}
        r = {x['check']: x['status'] for x in p.models(fetch)}
        self.assertEqual(r['model:llama3.2:3b-instruct-q4_K_M'], 'OK')
        self.assertEqual(r['model:muse-glimmer:30b-q4_K_M'], 'MISMATCH')

    def test_absent_services_are_optional(self):
        def down(url):
            raise OSError()
        self.assertTrue(all(x['status'] == 'OPTIONAL_ABSENT' and not x['required'] for x in p.models(down)))

    def test_only_meta_models_pinned(self):
        from src.ai.registry import META_MODELS
        self.assertTrue({m for m, _, _ in p.MODELS.values()} <= META_MODELS)

    def test_ready_depends_on_required_only(self):
        res = p.run_all(lambda url: (_ for _ in ()).throw(OSError()))
        self.assertIsInstance(p.ready(res), bool)
        self.assertTrue(any(r['check'] == 'python' for r in res))


if __name__ == '__main__':
    unittest.main()
