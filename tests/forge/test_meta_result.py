"""Campaign Two S4.7: the discriminated Meta result type itself.

Proposal | Clarification | Refusal, each explicitly validated. Only a
proposal yields a payload; refusal and clarification yield nothing
installable or executable, and a payload smuggled on either is rejected
as a whole.
"""
import unittest

from src.forge import meta_result


def echo(payload):
    return payload


class Discriminant(unittest.TestCase):
    def test_three_canonical_outcomes(self):
        self.assertEqual(meta_result.OUTCOMES, ('proposal', 'clarification', 'refusal'))

    def test_unknown_outcome_rejected(self):
        for bad in ('maybe', 'PROPOSAL', '', None, 0, ['proposal']):
            with self.assertRaises(meta_result.MetaError, msg=repr(bad)):
                meta_result.parse({'outcome': bad, 'patch': {}}, 'patch', echo)

    def test_missing_outcome_rejected(self):
        with self.assertRaises(meta_result.MetaError):
            meta_result.parse({'patch': {}}, 'patch', echo)

    def test_non_dict_and_unknown_keys_rejected(self):
        for bad in (None, [], 'proposal', {'outcome': 'refusal', 'reason': 'x', 'extra': 1}):
            with self.assertRaises(meta_result.MetaError, msg=repr(bad)):
                meta_result.parse(bad, 'patch', echo)

    def test_legacy_spellings_canonicalized(self):
        o, p, d, c = meta_result.parse(
            {'outcome': 'needs_clarification', 'clarifying_question': 'a or b?'}, 'patch', echo)
        self.assertEqual((o, p, c), ('clarification', None, None))
        self.assertIn('a or b', d)
        o, p, d, c = meta_result.parse(
            {'outcome': 'unsupported', 'reason': 'no such device'}, 'patch', echo)
        self.assertEqual((o, p, c), ('refusal', None, None))
        self.assertIn('device', d)


class Proposal(unittest.TestCase):
    def test_proposal_requires_and_validates_payload(self):
        seen = []

        def validate(payload):
            seen.append(payload)
            return {'valid': True}

        o, p, d, c = meta_result.parse(
            {'outcome': 'proposal', 'patch': {'a': 1}}, 'patch', validate)
        self.assertEqual((o, p, d, c), ('proposal', {'valid': True}, '', None))
        self.assertEqual(seen, [{'a': 1}])

    def test_proposal_without_payload_rejected(self):
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse({'outcome': 'proposal'}, 'patch', echo)
        self.assertIn('RESPONSE_PAYLOAD_MISSING', str(e.exception))

    def test_payload_validation_errors_propagate(self):
        def reject(payload):
            raise ValueError('UNKNOWN_BINDING')

        with self.assertRaises(ValueError) as e:
            meta_result.parse({'outcome': 'proposal', 'patch': {}}, 'patch', reject)
        self.assertIn('UNKNOWN_BINDING', str(e.exception))


class Refusal(unittest.TestCase):
    def test_refusal_yields_nothing_executable(self):
        o, p, d, c = meta_result.parse(
            {'outcome': 'refusal', 'reason': 'shell is not offered'}, 'patch', echo)
        self.assertEqual((o, p, c), ('refusal', None, None))
        self.assertIn('shell', d)

    def test_refusal_requires_nonempty_bounded_reason(self):
        for bad in ('', '   ', 'x' * 501, None, 42):
            with self.assertRaises(meta_result.MetaError, msg=repr(bad)[:20]):
                meta_result.parse({'outcome': 'refusal', 'reason': bad}, 'patch', echo)
        with self.assertRaises(meta_result.MetaError):
            meta_result.parse({'outcome': 'refusal'}, 'patch', echo)

    def test_refusal_detail_is_stripped(self):
        o, _, d, _ = meta_result.parse(
            {'outcome': 'refusal', 'reason': '  no  '}, 'patch', echo)
        self.assertEqual(d, 'no')

    def test_known_refusal_codes_accepted(self):
        for code in sorted(meta_result.REFUSAL_CODES):
            _, _, _, got = meta_result.parse(
                {'outcome': 'refusal', 'reason': 'x', 'code': code}, 'patch', echo)
            self.assertEqual(got, code)

    def test_unknown_refusal_code_rejected_whole(self):
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse(
                {'outcome': 'refusal', 'reason': 'x', 'code': 'EVERYTHING_IS_FINE'},
                'patch', echo)
        self.assertIn('RESPONSE_CODE', str(e.exception))

    def test_refusal_smuggling_payload_rejected_whole(self):
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse(
                {'outcome': 'refusal', 'reason': 'x', 'patch': {'a': 1}}, 'patch', echo)
        self.assertIn('RESPONSE_PATCH_WITH_REFUSAL', str(e.exception))


class Clarification(unittest.TestCase):
    def test_clarification_yields_nothing_executable(self):
        o, p, d, c = meta_result.parse(
            {'outcome': 'clarification', 'clarifying_question': 'TV or vacuum?'},
            'patch', echo)
        self.assertEqual((o, p, c), ('clarification', None, None))
        self.assertIn('vacuum', d)

    def test_clarification_requires_nonempty_bounded_question(self):
        for bad in ('', 'x' * 501, None):
            with self.assertRaises(meta_result.MetaError, msg=repr(bad)[:20]):
                meta_result.parse(
                    {'outcome': 'clarification', 'clarifying_question': bad}, 'patch', echo)
        with self.assertRaises(meta_result.MetaError):
            meta_result.parse({'outcome': 'clarification'}, 'patch', echo)

    def test_clarification_smuggling_payload_rejected_whole(self):
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse(
                {'outcome': 'clarification', 'clarifying_question': 'x?', 'steps': []},
                'steps', echo)
        self.assertIn('RESPONSE_STEPS_WITH_CLARIFICATION', str(e.exception))


class BidirectionalSmuggling(unittest.TestCase):
    """E1-B-W2/F-01: each outcome allows exactly its own keys."""

    def test_proposal_with_detail_keys_rejected(self):
        for key, val in (('reason', 'x'), ('code', 'UNSUPPORTED'),
                         ('clarifying_question', 'x?')):
            with self.assertRaises(meta_result.MetaError, msg=key) as e:
                meta_result.parse(
                    {'outcome': 'proposal', 'patch': {}, key: val}, 'patch', echo)
            self.assertIn('WITH_PROPOSAL', str(e.exception))

    def test_cross_detail_keys_rejected(self):
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse(
                {'outcome': 'refusal', 'reason': 'x', 'clarifying_question': 'y?'},
                'patch', echo)
        self.assertIn('RESPONSE_CLARIFYING_QUESTION_WITH_REFUSAL', str(e.exception))
        for key in ('reason', 'code'):
            with self.assertRaises(meta_result.MetaError, msg=key) as e:
                meta_result.parse(
                    {'outcome': 'clarification', 'clarifying_question': 'y?', key: 'x'},
                    'patch', echo)
            self.assertIn('WITH_CLARIFICATION', str(e.exception))

    def test_oversize_payload_rejected_before_validation(self):
        called = []

        def validate(payload):
            called.append(payload)
            return payload

        big = {'blob': 'x' * (meta_result.MAX_PAYLOAD_CHARS + 1)}
        with self.assertRaises(meta_result.MetaError) as e:
            meta_result.parse({'outcome': 'proposal', 'patch': big}, 'patch', validate)
        self.assertIn('RESPONSE_PAYLOAD_TOO_LARGE', str(e.exception))
        self.assertEqual(called, [])


if __name__ == '__main__':
    unittest.main()
