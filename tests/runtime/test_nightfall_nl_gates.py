"""NIGHTFALL F-05: strict model-reply shape validation in nl_router._interpret.

INTENT_SCHEMA promises maxItems 8 for targets, but _interpret never
enforced it; non-list ambiguities were iterated into characters; non-list
targets escaped as a raw TypeError instead of a terminal escalation.
All three are closed here: malformed shapes become escalation_required.
"""
import unittest


def _reply(**kw):
    base = {'outcome': 'count online devices', 'skill_id': 'fabric.status',
            'targets': [{'kind': 'category', 'ref': 'fabric'}], 'params': {},
            'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}
    base.update(kw)
    return base


def _parse(reply):
    from src.runtime import nl_router as N
    return N.parse('probe text', 'en', 'low', lambda prompt: reply)


class ReplyShapeValidation(unittest.TestCase):
    def test_nine_targets_escalate(self):
        doc = _parse(_reply(targets=[{'kind': 'device', 'ref': 'd%d' % i}
                                     for i in range(9)]))
        self.assertEqual(doc['status'], 'escalation_required')

    def test_eight_targets_resolve(self):
        doc = _parse(_reply(targets=[{'kind': 'device', 'ref': 'd%d' % i}
                                     for i in range(8)]))
        self.assertEqual(doc['status'], 'resolved')

    def test_string_ambiguities_escalate(self):
        doc = _parse(_reply(ambiguities='soon'))
        self.assertEqual(doc['status'], 'escalation_required')

    def test_string_targets_escalate_without_exception(self):
        doc = _parse(_reply(targets='tv'))
        self.assertEqual(doc['status'], 'escalation_required')

    def test_null_targets_escalate(self):
        doc = _parse(_reply(targets=None))
        self.assertEqual(doc['status'], 'escalation_required')

    def test_clarify_with_string_ambiguities_coerces(self):
        doc = _parse(_reply(skill_id=None, targets=[], confidence=0.0,
                            clarifying_question='Which one?',
                            ambiguities='soon'))
        self.assertEqual(doc['status'], 'needs_clarification')
        self.assertEqual(doc['ambiguities'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
