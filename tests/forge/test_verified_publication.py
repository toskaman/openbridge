import copy
from concurrent.futures import TimeoutError
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from src.forge.compiler import ForgeError
from src.forge.fixtures import manifest
from src.forge.service import ForgeService, MemoryProvider


class VerifiedPublicationTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.manifest = manifest(self.now)
        self.provider = MemoryProvider(self.manifest)
        self.service = ForgeService(self.provider, clock=lambda: self.now)

    def test_requires_exact_consent_before_reading_provider(self):
        def unexpected(_): raise AssertionError('No provider read without consent')
        self.provider.snapshot = unexpected
        for consent in (False, 'true', 1, None):
            with self.assertRaisesRegex(ForgeError, 'OWNER_CONSENT_REQUIRED'):
                self.service.publish_verified(self.manifest, consent=consent)
        self.assertEqual(self.service.list_services(), [])

    def test_success_contains_a_new_verified_read_not_cached_manifest(self):
        calls = []
        def snapshot(_):
            calls.append(1)
            current = copy.deepcopy(self.manifest)
            if len(calls) > 1: current['observations'][0]['rssi_dbm'] = -40
            return current
        self.provider.snapshot = snapshot
        result = self.service.publish_verified(self.manifest, consent=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['verification']['state'], 'verified')
        self.assertEqual(result['verification']['read']['observations'][0]['rssi_dbm'], -40)
        self.assertTrue(result['simulation'])
        self.assertEqual(len(self.service.list_services()), 1)

    def test_failed_verification_removes_only_new_service(self):
        for failure in ('permission', 'expired', 'provenance', 'provider'):
            with self.subTest(failure=failure):
                calls = []
                def snapshot(_):
                    calls.append(1)
                    current = copy.deepcopy(self.manifest)
                    if len(calls) > 1:
                        if failure == 'provider': raise OSError('private detail')
                        if failure == 'permission': current['permissions'] = []
                        if failure == 'expired': current['observed_at'] = self.now - 301
                        if failure == 'provenance': current['device_id'] = 'different-device'
                    return current
                self.provider.snapshot = snapshot
                with self.assertRaisesRegex(ForgeError, '^PUBLICATION_VERIFICATION_FAILED$'):
                    self.service.publish_verified(self.manifest, consent=True)
                self.assertEqual(self.service.list_services(), [])
                with self.assertRaisesRegex(ForgeError, 'SERVICE_REMOVED'):
                    self.service.read(self.manifest['service_id'])

    def test_existing_service_is_not_replaced_or_removed(self):
        self.service.publish(self.manifest, consent=True)
        def unexpected(_): raise AssertionError('Existing service must not be republished')
        self.provider.snapshot = unexpected
        with self.assertRaisesRegex(ForgeError, 'SERVICE_ALREADY_PUBLISHED'):
            self.service.publish_verified(self.manifest, consent=True)
        self.assertEqual(len(self.service.list_services()), 1)

    def test_concurrent_verified_creation_has_one_winner(self):
        def publish(_):
            try: return self.service.publish_verified(self.manifest, consent=True)['state']
            except ForgeError as error: return str(error)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(publish, range(8)))
        self.assertEqual(results.count('published'), 1)
        self.assertEqual(results.count('SERVICE_ALREADY_PUBLISHED'), 7)
        self.assertEqual(len(self.service.list_services()), 1)
    def test_unverified_intermediate_service_cannot_be_read(self):
        verifying=threading.Event();release=threading.Event();reading=threading.Event();calls=[]
        def snapshot(_):
            calls.append(1)
            current=copy.deepcopy(self.manifest)
            if len(calls)==2:
                verifying.set()
                if not release.wait(3):raise AssertionError('Test did not release verification')
                current['available']=False
            return current
        self.provider.snapshot=snapshot
        def publish():
            try:self.service.publish_verified(self.manifest,consent=True)
            except ForgeError as error:return str(error)
        def read():
            reading.set()
            try:self.service.read(self.manifest['service_id'])
            except ForgeError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            publisher=pool.submit(publish)
            try:
                self.assertTrue(verifying.wait(2))
                reader=pool.submit(read);self.assertTrue(reading.wait(2))
                with self.assertRaises(TimeoutError):reader.result(timeout=.05)
            finally:release.set()
            self.assertEqual(publisher.result(timeout=2),'PUBLICATION_VERIFICATION_FAILED')
            self.assertEqual(reader.result(timeout=2),'SERVICE_REMOVED')
