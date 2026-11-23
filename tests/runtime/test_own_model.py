"""OpenBridge's own command model is the official one: tried first everywhere a request is understood,
digest-pinned, and replaced by the general Llama 3.2 3B (with honest provenance) when it is absent."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.ai import own_model, registry
from src.runtime import command as C
from src.runtime import nl_router as NR

ROOT = Path(__file__).resolve().parents[2]


def reply(sid='vacuum.start'):
    return {'outcome': 'start cleaning', 'skill_id': sid, 'targets': [{'kind': 'device', 'ref': 'vacuum'}],
            'params': {}, 'confidence': 0.9, 'ambiguities': [], 'clarifying_question': None}


class Fake:
    def __init__(self, model_id, ready=True, out=None, error=None):
        self.model_id, self.endpoint, self._ready, self.out, self.error = model_id, 'http://127.0.0.1:1', ready, out, error
        self.calls, self.last_ok = 0, None

    def ready(self):
        return self._ready

    def __call__(self, prompt):
        self.calls += 1
        if self.error:
            self.last_ok = False
            raise self.error
        self.last_ok = True
        return self.out


class Official(unittest.TestCase):
    def test_declared_in_the_runtime_manifest(self):
        self.assertIn((own_model.MODEL_ID, own_model.ENDPOINT), registry.load())
        manifest = json.loads((ROOT / 'config' / 'runtime_models.json').read_text(encoding='utf-8'))
        first = manifest['model_calls'][0]
        self.assertEqual((first['model_id'], first['manifest_digest']), (own_model.MODEL_ID, own_model.MODEL_DIGEST))
        self.assertIn('official', first['purpose'])

    def test_server_low_tier_prefers_the_own_model(self):
        t = C._low(SimpleNamespace())
        self.assertIsInstance(t, NR.PreferredTransport)
        self.assertEqual((t.preferred.model_id, t.preferred.digest), (own_model.MODEL_ID, own_model.MODEL_DIGEST))
        self.assertEqual(t.fallback.model_id, NR.TIERS['low'][0])


class Preferred(unittest.TestCase):
    def test_own_model_answers_and_is_named(self):
        own, gen = Fake(own_model.MODEL_ID, out=reply()), Fake('llama', out=reply('fabric.status'))
        d = NR.parse('Start my vacuum', 'en', 'low', NR.PreferredTransport(own, gen), None)
        self.assertEqual((d['skill_id'], d['provenance']['model_id']), ('vacuum.start', own_model.MODEL_ID))
        self.assertEqual(gen.calls, 0)

    def test_absent_own_model_falls_back_with_honest_provenance(self):
        own, gen = Fake(own_model.MODEL_ID, ready=False), Fake('llama', out=reply())
        d = NR.parse('Start my vacuum', 'en', 'low', NR.PreferredTransport(own, gen), None)
        self.assertEqual(d['provenance']['model_id'], 'llama')
        self.assertEqual(own.calls, 0)

    def test_failing_own_model_falls_back_once(self):
        own = Fake(own_model.MODEL_ID, error=NR.TransportError('bad shape'))
        gen = Fake('llama', out=reply())
        t = NR.PreferredTransport(own, gen)
        self.assertEqual(NR.parse('Start my vacuum', 'en', 'low', t, None)['status'], 'resolved')
        self.assertEqual((own.calls, gen.calls, t.answered_by), (1, 1, 'llama'))

    def test_both_down_is_an_escalation_never_a_guess(self):
        t = NR.PreferredTransport(Fake(own_model.MODEL_ID, ready=False), Fake('llama', error=NR.TransportError('down')))
        self.assertEqual(NR.parse('Start my vacuum', 'en', 'low', t, None)['status'], 'escalation_required')

    def test_tiers_report_official_and_fallback(self):
        own, gen = Fake(own_model.MODEL_ID, ready=False), Fake('llama')
        srv = SimpleNamespace(command_low=NR.PreferredTransport(own, gen), command_medium=Fake('glimmer', ready=False))
        low = C.tiers(srv)['low']
        self.assertEqual((low['model'], low['official'], low['official_ready'], low['ready']), (own_model.MODEL_ID, True, False, True))
        self.assertEqual(low['fallback']['model'], NR.TIERS['low'][0])


if __name__ == '__main__':
    unittest.main()


class Hesitation(unittest.TestCase):
    """« sors les poubelles » must never empty the vacuum's dust bin: a request that does not name the device is asked back."""

    def parse(self, text, lang, sid):
        return NR.parse(text, lang, 'low', Fake('m', out=reply(sid)), None)

    def test_chores_that_do_not_name_the_device_are_asked_back(self):
        for text, lang in (('sors les poubelles', 'fr'), ('vide la poubelle de la cuisine', 'fr'),
                           ('take the trash out', 'en'), ('empty the bin', 'en'), ('vide le lave-vaisselle', 'fr')):
            with self.subTest(text=text):
                d = self.parse(text, lang, 'vacuum.empty_dust')
                self.assertEqual(d['status'], 'needs_clarification')
                self.assertIn('robot aspirateur' if lang == 'fr' else 'robot vacuum', d['clarifying_question'])
                self.assertTrue(any('device not mentioned' in a for a in d['ambiguities']))

    def test_real_device_requests_go_through_even_with_typos(self):
        for text, lang, sid in (("vide le bac de l'aspirateur", 'fr', 'vacuum.empty_dust'), ("Vide l'asiprateur", 'fr', 'vacuum.empty_dust'),
                                ('lance le méange', 'fr', 'vacuum.start'), ('Run the self-empty', 'en', 'vacuum.empty_dust'),
                                ('Nettoie le sol', 'fr', 'vacuum.start'), ('turn up the telly', 'en', 'tv_volume_step')):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text, lang, sid)['status'], 'resolved')

    def test_measured_on_the_training_generator(self):
        import sys
        sys.path.insert(0, str(ROOT / 'dev' / 'ai_training'))
        import make_dataset as V2
        train, test, novel, _, _ = V2.build(7)
        rows = [r for r in train + test + novel if (r['reply'].get('skill_id') or '').startswith(('vacuum.', 'tv_', 'app_'))]
        missed = [r['text'] for r in rows if not NR.mentions_device(NR._skill_family(r['reply']['skill_id']), r['text'])]
        self.assertLess(len(missed) / len(rows), 0.01, missed[:10])     # fewer than 1 % asked back (heavy typos)
