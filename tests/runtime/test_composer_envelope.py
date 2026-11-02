"""MI composer envelope: refusal/clarification are first-class composer
outcomes (parity with nl_plan S4.7), and the intent/effect gate guards
the composer path against semantic substitution.

Without this, the steps-only schema FORCES the model to guess steps for
impossible requests (MI-COMP dev-09/10/12/24: factory-reset and
turn-off-all composed into allowed tv_sleep steps).
"""
import json
import unittest


def _devices():
    return [{'key': 'dev-tv', 'label': 'Android TV', 'category': 'tv',
             'handles': {'WIFI': 'h'}}]


class ReadyRouter:
    def skill_routes(self, skill, key):
        return {'selected_route_id': 'rt', 'routes': [
            {'route_id': 'rt', 'state': 'READY',
             'hops': [{'transport': 'STUB', 'primitive_id': 'read_facts'}],
             'operation_id': 'op', 'evidence': 'stub'}], 'selection': {}}


class EnvelopeParse(unittest.TestCase):
    def test_bare_steps_still_accepted(self):
        from src.runtime import composer as comp
        doc = comp.proposal_from_reply(json.dumps(
            {'steps': [{'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]}))
        self.assertEqual(doc['steps'][0]['skill_id'], 'tv_sleep')

    def test_refusal_envelope_raises_with_model_words(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError) as e:
            comp.proposal_from_reply(json.dumps(
                {'outcome': 'refusal', 'reason': 'no such skill for formatting'}))
        self.assertIn('model refused', str(e.exception))
        self.assertIn('formatting', str(e.exception))

    def test_clarification_envelope_raises_with_question(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError) as e:
            comp.proposal_from_reply(json.dumps(
                {'outcome': 'clarification', 'clarifying_question': 'Which TV?'}))
        self.assertIn('model needs clarification', str(e.exception))
        self.assertIn('Which TV?', str(e.exception))

    def test_proposal_envelope_accepted(self):
        from src.runtime import composer as comp
        doc = comp.proposal_from_reply(json.dumps(
            {'outcome': 'proposal', 'steps': [
                {'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]}))
        self.assertEqual(doc['steps'][0]['skill_id'], 'tv_sleep')

    def test_smuggled_payload_on_refusal_rejected(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError):
            comp.proposal_from_reply(json.dumps(
                {'outcome': 'refusal', 'reason': 'x',
                 'steps': [{'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]}))

    def test_smuggled_reason_on_proposal_rejected(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError):
            comp.proposal_from_reply(json.dumps(
                {'outcome': 'proposal', 'reason': 'helpful', 'steps': [
                    {'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]}))

    def test_unknown_outcome_rejected(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError):
            comp.proposal_from_reply(json.dumps({'outcome': 'maybe'}))


class PromptV2(unittest.TestCase):
    def test_prompt_teaches_refusal_and_exact_labels(self):
        from src.runtime import composer as comp
        p = comp.build_prompt('Do something', _devices())
        self.assertIn('refusal', p)
        self.assertIn('clarification', p)
        self.assertIn('never shorten', p.lower())
        self.assertIn('must appear', p.lower())


class IntentGate(unittest.TestCase):
    def _proposer(self, steps):
        return lambda prompt: {'model_id': 'stub', 'endpoint': 'stub',
                               'content': json.dumps({'steps': steps})}

    def test_destructive_request_refused_despite_allowed_step(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError) as e:
            comp.propose_and_compose(
                'Factory-reset the TV.', _devices(), ReadyRouter(),
                self._proposer([{'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]))
        self.assertIn('refused', str(e.exception))

    def test_semantic_substitution_clarifies(self):
        from src.runtime import composer as comp
        with self.assertRaises(comp.ComposerError) as e:
            comp.propose_and_compose(
                'Show me the infos of the PC.', _devices(), ReadyRouter(),
                self._proposer([{'skill_id': 'pc_run', 'target': 'Android TV', 'params': {'command': 'whoami', 'timeout_s': 5}}]))
        self.assertIn('clarification', str(e.exception))

    def test_matching_proposal_passes_gate(self):
        from src.runtime import composer as comp
        out = comp.propose_and_compose(
            'Put the TV to sleep.', _devices(), ReadyRouter(),
            self._proposer([{'skill_id': 'tv_sleep', 'target': 'Android TV', 'params': {}}]))
        self.assertEqual(out['steps'][0]['status'], 'allowed')

    def test_new_vocab_passes_sleep_wake_foreground(self):
        from src.runtime import composer as comp
        for text, skill in [('Put the TV to sleep.', 'tv_sleep'),
                            ('Wake the TV.', 'tv_wake'),
                            ('Bring the app to the front.', 'companion_foreground'),
                            ('Mets la télé en veille.', 'tv_sleep'),
                            ('Réveille la télévision.', 'tv_wake')]:
            out = comp.propose_and_compose(
                text, _devices(), ReadyRouter(),
                self._proposer([{'skill_id': skill, 'target': 'Android TV', 'params': {}}]))
            self.assertEqual(out['steps'][0]['status'], 'allowed', text)

    def test_response_schema_has_envelope(self):
        from src.runtime import composer as comp
        self.assertIn('outcome', comp.COMPOSER_RESPONSE_SCHEMA['properties'])
        self.assertIn('steps', comp.COMPOSER_RESPONSE_SCHEMA['properties'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
