"""Unit tests for src/ai/voice_normalize.py (Campaign Two §4.6).

Pins the folding/repair/language primitives, every screen's hit and miss
sides (including false-positive guards on real product phrases), and the
drain entry point contract. The end-to-end corpus lives in
test_voice_flow_corpus.py.
"""
import unittest

from src.ai import voice_normalize as VN

# Real product phrases that must NEVER trip a screen (false-positive guards).
CLEAN = (
    'Find the nearby Bluetooth devices through the living-room TV',
    'Trouve les appareils Bluetooth via la télé du salon',
    'Pourquoi la télé se déconnecte ?',
    'Why does my phone disconnect?',
    'Découvre mes appareils',
    'Fais un diagnostic',
    'Termine la session',
    'Discover all my devices',
    'Run a bluetooth scan via the tv',
    'Start a bluetooth scan with my phone',
    'Run a full diagnostic report',
    'Why does the tv keep disconnecting?',
    'Finish the session and restore',
    'allume la lampe du salon',
    'allume la lampe',
    'Monte le son',
    "Mets l'aspirateur en pause",
    'vide le bac à poussière de mon aspirateur',
)


class FoldRepair(unittest.TestCase):
    def test_fold_strips_accents_case_and_punctuation(self):
        self.assertEqual(VN.fold('Pourquoi la télé se déconnecte ?'),
                         'pourquoi la tele se deconnecte')
        self.assertEqual(VN.fold("L'porte d'entrée"), 'l porte d entree')
        self.assertEqual(VN.fold('  Scan   TV  '), 'scan tv')
        self.assertEqual(VN.fold(None), '')
        self.assertEqual(VN.fold(42), '')

    def test_single_reading_repairs(self):
        fixed, repairs = VN.repair('mas les boutons de volume sur la tellee')
        self.assertIn('tellee->tele', repairs)
        self.assertIn('tele', fixed.split())
        fixed, repairs = VN.repair('blue tooth via the tv')
        self.assertIn('blue tooth->bluetooth', repairs)
        fixed, repairs = VN.repair('move it from my free box to the tv')
        self.assertIn('free box->freebox', repairs)
        fixed, repairs = VN.repair('active le bloutouth sur la tele')
        self.assertIn('bloutouth->bluetooth', repairs)

    def test_telle_repaired_only_in_device_position(self):
        fixed, repairs = VN.repair('bluetooth via la telle')
        self.assertEqual(repairs, ['telle->tele'])
        self.assertTrue(fixed.endswith('la tele'))
        fixed, repairs = VN.repair('une telle option de scan')
        self.assertEqual((fixed, repairs), ('une telle option de scan', []))

    def test_clean_text_has_no_repairs(self):
        for text in CLEAN:
            with self.subTest(text=text[:30]):
                self.assertEqual(VN.repair(VN.fold(text))[1], [])


class Language(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(VN.detect_lang('mas les boutons de volume sur la tellée'), 'fr')
        self.assertEqual(VN.detect_lang('Find the nearby Bluetooth devices'), 'en')
        self.assertEqual(VN.detect_lang('allume la lampe du salon'), 'fr')
        self.assertEqual(VN.detect_lang('Lance un scan bluetooth via la télé'), 'fr')

    def test_loanwords_and_empty_are_unknown(self):
        for text in ('scan', 'volume', 'bluetooth', 'tv', ''):
            with self.subTest(text=text):
                self.assertEqual(VN.detect_lang(text), 'unknown')

    def test_hint_only_fills_unknown(self):
        self.assertEqual(VN.lang_or_hint('scan', 'fr'), 'fr')
        self.assertEqual(VN.lang_or_hint('scan', None), 'en')
        self.assertEqual(VN.lang_or_hint('allume la lampe', 'en'), 'fr')


class UncertainVerb(unittest.TestCase):
    def test_watch7_shapes_are_uncertain(self):
        for text in ('mas les boutons de volume sur la tellee',
                     'mais les boutons de volume sur la tellee',
                     'mes boutons de volume sur la tele'):
            with self.subTest(text=text[:20]):
                self.assertTrue(VN.uncertain_verb(VN.fold(text)))

    def test_conjunction_mais_stays_trusted(self):
        self.assertFalse(VN.uncertain_verb(VN.fold('mais fais un diagnostic')))
        self.assertFalse(VN.uncertain_verb(VN.fold('decouvre tous mes appareils')))
        self.assertFalse(VN.uncertain_verb(VN.fold('mets les boutons sur la tele')))


class Screens(unittest.TestCase):
    def test_refusal_extra_hits(self):
        for text in ('reboot the tv', 'redemarre la tele', 'restart my phone',
                     'wipe everything', 'efface tout', 'erase the disk',
                     'format the drive', 'flash the firmware',
                     'flashe mon telephone', 'brick it', 'unlock my phone',
                     'deverrouille mon telephone', 'ouvre la porte',
                     'open the front door', 'buy this app', 'pay now',
                     'achete cette application'):
            with self.subTest(text=text):
                self.assertTrue(VN.screen_refusal_extra(VN.fold(text)), text)

    def test_refusal_extra_misses(self):
        for text in ('allume le flash de mon telephone', 'quel pays',
                     "je m'appelle marc", 'vide le bac de mon aspirateur',
                     'affiche la video') + CLEAN:
            with self.subTest(text=text[:30]):
                self.assertIsNone(VN.screen_refusal_extra(VN.fold(text)), text)

    def test_conflict_hits(self):
        cases = (
            ('decouvre mes appareils et termine la session', 'finish'),
            ('finish the session and scan for bluetooth', 'finish'),
            ('scan bluetooth via the tv and the phone', 'targets'),
            ('start and stop the vacuum', 'startstop'),
            ('demarre puis arrete l aspirateur', 'startstop'),
        )
        for text, kind in cases:
            with self.subTest(text=text[:30]):
                hit = VN.screen_conflict(VN.fold(text))
                self.assertTrue(hit, text)
                self.assertEqual(hit['kind'], kind)

    def test_conflict_misses(self):
        for text in ('start cleaning with the vacuum',
                     'lance un scan bluetooth via la tele',
                     'termine la session',
                     'finish the session and restore',
                     'pause the vacuum',
                     "mets l'aspirateur en pause") + CLEAN:
            with self.subTest(text=text[:30]):
                self.assertIsNone(VN.screen_conflict(VN.fold(text)), text)

    def test_press_hits_and_misses(self):
        for text in ('press volume plus on the watch',
                     'appuie sur le bouton scan de la montre',
                     'tap the youtube button',
                     'clique sur le bouton volume'):
            with self.subTest(text=text):
                self.assertTrue(VN.screen_control_press(VN.fold(text)), text)
        for text in ('monte le son de la tele',
                     'set the volume to 20 on the tv',
                     'mets les boutons sur la tele') + CLEAN:
            with self.subTest(text=text[:30]):
                self.assertIsNone(VN.screen_control_press(VN.fold(text)), text)

    def test_migration_hits_and_misses(self):
        # Screens run on repaired text in production; STT spellings (tellee)
        # only resolve there.
        for text in ('enleve les boutons de volumes de la montre et met les bouton',
                     'mas les boutons de volume sur la tellee',
                     'mais les boutons de volume sur la tellee',
                     'mets les boutons sur la tele',
                     'put the volume buttons on the tv',
                     'remove the volume controls from my watch'):
            with self.subTest(text=text[:30]):
                fixed = VN.repair(VN.fold(text))[0]
                self.assertTrue(VN.screen_migration_shape(fixed), text)
        for text in ('mets le volume sur la tele',
                     'monte le son de la tele',
                     'press volume plus on the watch') + CLEAN:
            with self.subTest(text=text[:30]):
                fixed = VN.repair(VN.fold(text))[0]
                self.assertIsNone(VN.screen_migration_shape(fixed), text)

    def test_volume_hits_and_misses(self):
        for text in ('volume', 'plus fort', 'monte le son',
                     'monte le son de la tele',
                     'set the volume to 20 on the tv', 'baisse le son',
                     'turn it up louder on the tv'):
            with self.subTest(text=text):
                self.assertTrue(VN.screen_volume_shape(VN.fold(text)), text)
        # 'Monte le son' is a genuine volume shape, so it is asserted above
        # as a hit and excluded from the miss side here.
        misses = [t for t in CLEAN if t != 'Monte le son']
        for text in ('termine la session', 'fais un diagnostic',
                     'la tele', 'bluetooth',
                     'look up the tv manual') + tuple(misses):
            with self.subTest(text=text[:30]):
                self.assertIsNone(VN.screen_volume_shape(VN.fold(text)), text)

    def test_locate_hits_and_misses(self):
        for text in ('find my phone', 'retrouve mon telephone',
                     'where is my phone', 'ou est mon telephone'):
            with self.subTest(text=text):
                self.assertTrue(VN.screen_locate_shape(VN.fold(text)), text)
        for text in ('find the nearby bluetooth devices through the tv',
                     'where is the vacuum make it beep',
                     "ou est l'aspirateur fais le biper",
                     'trouve les appareils bluetooth',
                     'discover all my devices') + CLEAN:
            with self.subTest(text=text[:30]):
                self.assertIsNone(VN.screen_locate_shape(VN.fold(text)), text)

    def test_fragments(self):
        self.assertTrue(VN.is_fragment_match('discover', 'scan'))
        self.assertTrue(VN.is_fragment_match('diagnose', 'check'))
        self.assertFalse(VN.is_fragment_match('discover', 'decouvre mes appareils'))
        self.assertFalse(VN.is_fragment_match('diagnose', 'fais un diagnostic complet'))
        self.assertFalse(VN.is_fragment_match('ble_scan_via_tv', 'bluetooth tv'))
        self.assertTrue(VN.is_short('la tele'))
        self.assertTrue(VN.is_short('bluetooth'))
        self.assertFalse(VN.is_short('what is the weather'))
        self.assertFalse(VN.is_short(''))


class ControlReference(unittest.TestCase):
    def test_revoked_label(self):
        out = VN.check_control_reference(
            VN.fold('press the old Volume plus button'),
            revoked_labels=['Volume +'])
        self.assertEqual(out['verdict'], 'revoked')

    def test_stale_id(self):
        out = VN.check_control_reference(
            VN.fold('press ctl-a97523a98e-g1 to scan'),
            active_ids=['ctl-a97523a98e-g9'])
        self.assertEqual(out['verdict'], 'revoked')

    def test_live_id_and_label(self):
        out = VN.check_control_reference(
            VN.fold('press ctl-a97523a98e-g9 to scan'),
            active_ids=['ctl-a97523a98e-g9'])
        self.assertEqual(out['verdict'], 'press_active')
        out = VN.check_control_reference(
            VN.fold('tap the YouTube button'),
            active_labels=['YouTube'], revoked_labels=['Volume +'])
        self.assertEqual(out['verdict'], 'press_active')

    def test_unknown_press_and_none(self):
        out = VN.check_control_reference(VN.fold('tap the YouTube button'))
        self.assertEqual(out['verdict'], 'press_unknown')
        out = VN.check_control_reference(VN.fold('allume la lampe'))
        self.assertEqual(out['verdict'], 'none')


class Localization(unittest.TestCase):
    def test_every_question_is_bilingual(self):
        for kind, texts in VN.QUESTIONS.items():
            with self.subTest(kind=kind):
                self.assertTrue(texts['en'].strip())
                self.assertTrue(texts['fr'].strip())
                self.assertNotEqual(texts['en'], texts['fr'])

    def test_question_helpers(self):
        self.assertIn('session', VN.conflict_finish_question('discover', 'fr'))
        self.assertIn('TV', VN.repaired_question('ble_scan_via_tv', 'en'))
        self.assertIn('télé', VN.repaired_question('ble_scan_via_tv', 'fr'))


class DrainEntry(unittest.TestCase):
    def test_screens_map_to_drain_statuses(self):
        hit = VN.screen_voice_transcript('start and stop the vacuum', 'en')
        self.assertEqual(hit['status'], 'needs_clarification')
        hit = VN.screen_voice_transcript('reboot the tv', 'en')
        self.assertEqual((hit['status'], 'manual' in hit['text'].lower()),
                         ('unsupported', True))
        hit = VN.screen_voice_transcript('redemarre la tele', 'fr')
        self.assertIn('manuelle', hit['text'])

    def test_model_routed_transcripts_pass_through(self):
        for text in ('allume la lampe', 'monte le son',
                     'baisse le volume de la tv', 'start cleaning',
                     "mets l'aspirateur en pause", ''):
            with self.subTest(text=text):
                self.assertIsNone(VN.screen_voice_transcript(text, 'fr'), text)


if __name__ == '__main__':
    unittest.main()
