"""V4-10 voice: typed intents only, refusal of risky requests, STT client against a fake WebSocket (SIMULATED)."""
import base64
import json
import os
import struct
import unittest

from src.ai import voice_intent as vi

DEV = [{'key': 'dev-tv', 'category': 'tv'}, {'key': 'dev-ph', 'category': 'phone'}]


class Intents(unittest.TestCase):
    def test_sample_phrases_fr_en(self):
        cases = {
            'Find the nearby Bluetooth devices through the living-room TV': ('ble_scan_via_tv', 'dev-tv'),
            'Trouve les appareils Bluetooth via la télé du salon': ('ble_scan_via_tv', 'dev-tv'),
            'Pourquoi la télé se déconnecte ?': ('why_disconnect', 'dev-tv'),
            'Why does my phone disconnect?': ('why_disconnect', 'dev-ph'),
            'Découvre mes appareils': ('discover', 'fabric'),
            'Fais un diagnostic': ('diagnose', 'fabric'),
            'Termine la session': ('finish_session', 'fabric'),
        }
        for phrase, (intent, dev) in cases.items():
            with self.subTest(phrase=phrase):
                p = vi.compile_intent(phrase, DEV)
                self.assertEqual((p['intent'], p['device_key']), (intent, dev))
                self.assertIn('Proposal only', p['note'])

    def test_risky_or_unknown_requests_never_become_intents(self):
        for phrase in ('Éteins la télé', 'shutdown the TV', 'install this app', 'factory reset the router', 'what is the weather',
                       'adb shell rm -rf /', '', 'x' * 500, 'mot de passe du wifi'):
            with self.subTest(phrase=phrase[:30]):
                self.assertIsNone(vi.compile_intent(phrase, DEV)['intent'])

    def test_ambiguous_target_asks(self):
        p = vi.compile_intent('Bluetooth through the TV', DEV + [{'key': 'dev-tv2', 'category': 'tv'}])
        self.assertTrue(p['needs_target'])
