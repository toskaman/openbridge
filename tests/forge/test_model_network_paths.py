"""Blocked socket/DNS traces of actual model HTTP transport paths.

No packets reach a provider/model, and every key/credit permit is synthetic.
This is Python in-process transport coverage, not subprocess or OS egress control.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.ai.broker import CreditPermit, MetaTransport, ModelBlocked
from src.ai.glimmer import GlimmerBroker
from src.ai.local_meta import LocalMetaBroker, local_request
from src.ai.registry import RegistryInvalid, require
from src.forge.compiler import ForgeError
from src.forge.fixtures import manifest
from src.forge.local_models import IsolatedGlimmerCPU
from src.forge.planner_v2 import SchemaConstrainedPlanner
from src.forge.spark_diagnostic import SparkDiagnostic
from tests.unit.test_meta_only_network_trace import ALLOWED, Trace


class ModelNetworkPathTests(unittest.TestCase):
    def assert_endpoint(self, seen, endpoint):
        self.assertTrue(seen, 'No connection attempt means transport coverage was not exercised')
        self.assertEqual(set(seen), {endpoint})
        self.assertTrue(all(destination in ALLOWED for destination in seen))
        self.assertEqual(len(seen), 1, 'No automatic retry should occur after blocked connect')

    @staticmethod
    def pinned_catalog(cls):
        return lambda: {'models': [{'name': cls.model_id, 'digest': 'sha256:' + cls.model_digest}]}

    def test_complete_v2_chat_paths_reach_exact_pinned_local_endpoint(self):
        # Inject only the catalog: ready succeeds without querying a real service.
        # Keep broker._call/chat/local_request and urllib transport real until Trace refuses connect.
        for cls, port in ((LocalMetaBroker, 11437), (GlimmerBroker, 11438), (IsolatedGlimmerCPU, 11439)):
            with self.subTest(broker=cls.__name__), Trace() as trace:
                broker = cls(catalog=self.pinned_catalog(cls))
                with patch('src.ai.local_meta.local_request', wraps=local_request) as request:
                    with self.assertRaisesRegex(ForgeError, 'META_RESPONSE_FAILED'):
                        SchemaConstrainedPlanner(broker).plan([manifest(1800000000)], 1800000000)
                request.assert_called_once()
                self.assertEqual(request.call_args.args[0], '/api/chat')
                self.assertEqual(request.call_args.kwargs['endpoint'], broker.endpoint)
                self.assertEqual(request.call_args.args[1]['model'], broker.model_id)
            self.assert_endpoint(trace.seen, ('127.0.0.1', port))

    def test_pinned_cpu_prepare_and_release_reach_real_chat_transport(self):
        for operation, keep_alive in (('prepare', '5m'), ('release', 0)):
            with self.subTest(operation=operation), Trace() as trace:
                broker = IsolatedGlimmerCPU(catalog=self.pinned_catalog(IsolatedGlimmerCPU))
                planner = SchemaConstrainedPlanner(broker)
                with patch('src.ai.local_meta.local_request', wraps=local_request) as request:
                    with self.assertRaisesRegex(ForgeError, 'MODEL_CONTROL_FAILED'):
                        getattr(planner, operation)()
                request.assert_called_once()
                self.assertEqual(request.call_args.args[0], '/api/chat')
                payload = request.call_args.args[1]
                self.assertEqual(payload['model'], broker.model_id)
                self.assertEqual(payload['keep_alive'], keep_alive)
                self.assertNotIn('messages', payload)
            self.assert_endpoint(trace.seen, ('127.0.0.1', 11439))

    def test_unsupported_local_control_paths_fail_without_network(self):
        # Base Llama/Glimmer have no pinned control API; do not invent a generic one.
        for cls in (LocalMetaBroker, GlimmerBroker):
            for operation in ('prepare', 'release'):
                with self.subTest(broker=cls.__name__, operation=operation), Trace() as trace:
                    planner = SchemaConstrainedPlanner(cls(catalog=self.pinned_catalog(cls)))
                    with self.assertRaisesRegex(ForgeError, 'MODEL_CONTROL_UNAVAILABLE'):
                        getattr(planner, operation)()
                self.assertEqual(trace.seen, [])

    def test_digest_mismatch_blocks_chat_and_model_control_before_transport(self):
        for cls in (LocalMetaBroker, GlimmerBroker, IsolatedGlimmerCPU):
            with self.subTest(broker=cls.__name__), Trace() as trace:
                broker = cls(catalog=lambda: {'models': [{'name': cls.model_id, 'digest': 'wrong'}]})
                with self.assertRaisesRegex(ForgeError, 'META_UNAVAILABLE'):
                    SchemaConstrainedPlanner(broker).plan([manifest(1800000000)], 1800000000)
                if cls is IsolatedGlimmerCPU:
                    for operation in ('prepare', 'release'):
                        with self.assertRaisesRegex(ForgeError, 'META_UNAVAILABLE'):
                            getattr(SchemaConstrainedPlanner(broker), operation)()
            self.assertEqual(trace.seen, [])

    def test_spark_diagnostic_real_meta_transport_and_retained_fake_reservation(self):
        with TemporaryDirectory() as directory, Trace() as trace:
            budget = Path(directory) / 'synthetic-test-budget.sqlite'
            permit = CreditPermit('fake-transport-trace', datetime.now(timezone.utc), 150, .10)
            broker = SparkDiagnostic(budget, permit, MetaTransport('fake-key-never-transmitted'))
            with self.assertRaisesRegex(ModelBlocked, 'Diagnostic failed; reservation retained'):
                broker.diagnose('blocked_relay')
            self.assert_endpoint(trace.seen, ('api.meta.ai', 443))
            # No automatic retry; a second explicit attempt is blocked by the fake local allowance.
            with self.assertRaisesRegex(ModelBlocked, 'budget exhausted'):
                broker.diagnose('blocked_relay')
            self.assert_endpoint(trace.seen, ('api.meta.ai', 443))
            with closing(sqlite3.connect(budget)) as database:
                self.assertEqual(database.execute('SELECT SUM(reserved) FROM reservations').fetchone()[0], 100000)

    def test_undeclared_endpoint_and_non_meta_config_fail_before_transport(self):
        with TemporaryDirectory() as directory, Trace() as trace:
            path = Path(directory) / 'runtime-models.json'
            path.write_text(json.dumps({'environment': 'runtime', 'model_calls': [
                {'model_id': LocalMetaBroker.model_id, 'endpoint': 'http://127.0.0.1:11437', 'execution': 'local'}]}),
                                encoding='utf-8')
            with self.assertRaisesRegex(RegistryInvalid, 'not declared'):
                require(LocalMetaBroker.model_id, 'http://127.0.0.1:9999', path)
            path.write_text(json.dumps({'environment': 'runtime', 'model_calls': [
                {'model_id': LocalMetaBroker.model_id, 'endpoint': 'https://example.invalid', 'execution': 'local'}]}),
                                encoding='utf-8')
            with self.assertRaisesRegex(RegistryInvalid, 'Unapproved runtime model endpoint'):
                require(LocalMetaBroker.model_id, 'https://example.invalid', path)
            broker = LocalMetaBroker(catalog=self.pinned_catalog(LocalMetaBroker))
            broker.model_id = 'unapproved.model'
            with self.assertRaisesRegex(ForgeError, 'UNAPPROVED_META_MODEL'):
                SchemaConstrainedPlanner(broker)
        self.assertEqual(trace.seen, [])


if __name__ == '__main__':
    unittest.main()
