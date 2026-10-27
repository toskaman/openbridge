"""V4-05 cloud escalation: preview == bytes sent, consent per payload, untrusted answer (SIMULATED transport)."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.ai.broker import RuntimeModelBroker, CreditPermit, ModelBlocked
from src.ai.cloud_escalation import CloudEscalation
from src.runtime import hypotheses, redact
from src.runtime.timeline import Timeline


def scenario():
    tl = Timeline(clock=lambda: 0)
    tl.observe('dev-3f2a9c1b77aa', 'tv', 'link', 'up', 'ADB 192.168.1.15:5555', t=0)
    tl.observe('router-key', 'router', 'wifi_channel_5G', 36, 'GET wifi/ap/ Freebox-7A1B2C', t=0)
    tl.observe('router-key', 'router', 'wifi_channel_5G', 100, 'GET wifi/ap/', t=600)
    tl.observe('dev-3f2a9c1b77aa', 'tv', 'link', 'lost', 'read_facts DEVICE_UNAVAILABLE', t=612)
    rows = tl.rows()
    return hypotheses.analyze(rows, 'dev-3f2a9c1b77aa'), rows


def answer(content, model='muse-spark-1.3'):
    return {'model': model, 'id': 'req-1', 'usage': {'prompt_tokens': 300, 'completion_tokens': 900},
            'choices': [{'message': {'content': content if isinstance(content, str) else json.dumps(content)}}]}


GOOD = {'ranking': ['router_radio_change', 'unobserved_cause'], 'summary': 'The link loss is consistent with the channel change.',
        'uncertainty': 'One occurrence only.', 'next_read_only_check': 'Re-read the TV link and router channel for 10 minutes.'}


class Escalation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sent = []
        self.reply = answer(GOOD)

    def esc(self, permit=True):
        p = CreditPermit('t', datetime.now(timezone.utc), 150, 0.20) if permit else None
        b = RuntimeModelBroker(Path(self.tmp.name) / 'b.sqlite', p, transport=lambda pl: (self.sent.append(pl), self.reply)[1])
        return CloudEscalation(b)

    def test_preview_has_no_identifier_and_is_exactly_what_is_sent(self):
        e = self.esc()
        pv = e.preview(*scenario())
        self.assertEqual(redact.scan(pv['outgoing_payload']), [])
        for secret in ('dev-3f2a9c1b77aa', '192.168.1.15', 'Freebox-7A1B2C', 'router-key'):
            self.assertNotIn(secret, pv['outgoing_payload'])
        self.assertEqual(pv['sha256'], hashlib.sha256(pv['outgoing_payload'].encode()).hexdigest())
        r = e.confirm(pv['preview_id'], pv['sha256'], True)
        self.assertEqual(self.sent[0]['messages'][1]['content'], pv['outgoing_payload'])
        self.assertEqual(r['state'], 'LIVE')
        self.assertEqual(r['answer']['ranking'][0], 'router_radio_change')
        self.assertNotIn('outgoing_payload', json.dumps(r['receipt']))

    def test_no_consent_wrong_hash_or_reuse_sends_nothing(self):
        e = self.esc()
        pv = e.preview(*scenario())
        with self.assertRaises(ModelBlocked):
            e.confirm(pv['preview_id'], pv['sha256'], False)
        with self.assertRaises(ModelBlocked):
            e.confirm(pv['preview_id'], '0' * 64, True)
        pv = e.preview(*scenario())
        e.confirm(pv['preview_id'], pv['sha256'], True)
        with self.assertRaises(ModelBlocked):
            e.confirm(pv['preview_id'], pv['sha256'], True)     # one consent = one payload
        self.assertEqual(len(self.sent), 1)

    def test_unavailable_without_permit_never_pretends_live(self):
        e = CloudEscalation(None)
        pv = e.preview(*scenario())
        self.assertFalse(pv['live_available'])
        with self.assertRaises(ModelBlocked):
            e.confirm(pv['preview_id'], pv['sha256'], True)
        self.assertEqual(e.receipts[-1]['decision'], 'UNAVAILABLE')

    def test_untrusted_answers_are_rejected(self):
        bad = [dict(GOOD, ranking=['made_up']), dict(GOOD, summary='Caused by the router at 192.168.1.1'),
               dict(GOOD, next_read_only_check='run adb shell reboot'), dict(GOOD, extra='x'), 'not json']
        for content in bad:
            with self.subTest(content=str(content)[:40]):
                self.reply = answer(content)
                e = self.esc()
                pv = e.preview(*scenario())
                with self.assertRaises(ModelBlocked):
                    e.confirm(pv['preview_id'], pv['sha256'], True)
        self.reply = answer(GOOD, model='other-model')
        e = self.esc(); pv = e.preview(*scenario())
        with self.assertRaises(ModelBlocked):
            e.confirm(pv['preview_id'], pv['sha256'], True)

    def test_no_symptom_nothing_to_escalate(self):
        tl = Timeline(clock=lambda: 0); tl.observe('d', 'tv', 'link', 'up', t=0)
        with self.assertRaises(ModelBlocked):
            self.esc().preview(hypotheses.analyze(tl.rows(), 'd'), tl.rows())


if __name__ == '__main__':
    unittest.main()
