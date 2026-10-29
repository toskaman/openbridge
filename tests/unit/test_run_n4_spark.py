"""N4 runner: dry-run purity, pack validation, hermetic reserve-then-stop."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import dev.run_n4_spark as R


def good_reply():
    return {'outcome': 'start', 'skill_id': 'vacuum.start',
            'targets': [{'kind': 'category', 'ref': 'vacuum'}],
            'params': {}, 'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}


def cloud_response(content):
    return {'model': 'muse-spark-1.3', 'id': 't', 'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
            'choices': [{'message': {'content': content}}]}


def hermetic_factory(ledger, age_hours=0):
    from src.ai.broker import CreditPermit, RuntimeModelBroker
    permit = CreditPermit(observation_id='obs-test',
                          verified_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
                          free_balance_usd=135.0, session_budget_usd=0.20)
    sender = mock.Mock(side_effect=lambda p: cloud_response(json.dumps(good_reply())))
    broker = RuntimeModelBroker(ledger, permit, sender,
                                evaluation_allowance_usd=0.40, evaluation_authz='owner-test-ref')
    broker.sender_mock = sender
    return broker


class N4Runner(unittest.TestCase):
    def test_dry_run_no_reserve_no_network(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(R.sys, 'argv', ['prog', '--dry-run']):
                self.assertEqual(R.main(), 0)

    def test_pack_loads_4_frozen_cases(self):
        pack = R.load_pack()
        self.assertEqual(pack['pack'], 'n4-spark-vs-local')
        self.assertEqual(len(pack['cases']), 4)
        self.assertEqual(pack['budget_calls_max'], 4)

    def test_pack_rejects_bad_lang(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'pack.json'
            p.write_text(json.dumps({'budget_calls_max': 1, 'cases': [{'text': 'x', 'lang': 'de'}]}),
                         encoding='utf-8')
            with self.assertRaises(ValueError):
                R.load_pack(p)

    def test_no_ledger_override_flag(self):
        argv = ['prog', '--observation-id', 'o', '--free-balance-usd', '1', '--out', 'd',
               '--observed-at', '2026-10-29T06:00:00+00:00', '--authz', 'a', '--ledger', 'other.db']
        with mock.patch.object(R.sys, 'argv', argv), self.assertRaises(SystemExit) as cm:
            R.main()
        self.assertEqual(cm.exception.code, 2)

    def test_happy_path_reserves_once_per_case_hermetic(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            ledger = str(Path(d) / 'budget.sqlite3')
            brokers = []

            def factory():
                b = hermetic_factory(ledger)
                brokers.append(b)
                return b
            out = str(Path(d) / 'out')
            records, stopped = R.run_pack(
                factory, [{'prompt_id': 'P8', 'text': 'start my vacuum', 'lang': 'en'}], out)
            self.assertIsNone(stopped)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['status'], 'resolved')
            self.assertEqual(records[0]['skill_id'], 'vacuum.start')
            self.assertEqual(records[0]['reserved_usd'], 0.10)
            db = sqlite3.connect(ledger)
            self.assertEqual(db.execute('SELECT COUNT(*), SUM(reserved) FROM reservations').fetchone(), (1, 100000))
            db.close()
            self.assertEqual(brokers[0].sender_mock.call_count, 1)
            self.assertTrue((Path(out) / 'replies.json').exists())

    def test_expired_observation_stops_with_no_spend_no_call(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            ledger = str(Path(d) / 'budget.sqlite3')
            brokers = []

            def factory():
                b = hermetic_factory(ledger, age_hours=25)
                brokers.append(b)
                return b
            records, stopped = R.run_pack(
                factory, [{'prompt_id': 'P8', 'text': 'start my vacuum', 'lang': 'en'},
                          {'prompt_id': 'P7', 'text': 'allume la lampe du salon', 'lang': 'fr'}],
                str(Path(d) / 'out'))
            self.assertTrue(stopped.startswith('GATE'))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['status'], 'escalation_required')
            self.assertFalse(Path(ledger).exists())
            self.assertEqual(brokers[0].sender_mock.call_count, 0)


if __name__ == '__main__':
    unittest.main()
