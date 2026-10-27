"""Manual2Skill compiler slice: structured manual fragment -> guarded skill + provenance + trace replay.

Deterministic compile+verify half. LLM extraction (manual text -> fragment) is a separate
measured probe, not claimed here.
"""
import hashlib
import json
import unittest

from src.forge.manual_skill import ManualSkillError, compile_skill, render_command, replay


def fragment():
    return {'name': 'capture_waveform', 'version': '1.0.0', 'title': 'Oscilloscope manual excerpts',
            'parameters': [{'name': 'volts_per_div', 'unit': 'V', 'min': 0.1, 'max': 10.0, 'cite': 'manual.pdf:12'}],
            'warnings': [{'text': 'Never exceed 10 V on CH1.', 'cite': 'manual.pdf:14'},
                         {'text': 'Keep the bench dry.', 'cite': 'manual.pdf:15'}],
            'commands': [{'template': 'MEAS:CH1:RANGE {volts_per_div}V', 'cite': 'manual.pdf:12'}]}


class ManualSkillTests(unittest.TestCase):
    def test_compile_grounds_guards_and_provenance(self):
        skill = compile_skill(fragment())
        self.assertEqual(skill['name'], 'capture_waveform')
        self.assertIn('manual.pdf:12', skill['provenance']); self.assertIn('manual.pdf:14', skill['provenance'])
        self.assertEqual(render_command(skill, {'volts_per_div': 2.0}), 'MEAS:CH1:RANGE 2.0V')
        with self.assertRaisesRegex(ManualSkillError, 'manual.pdf:14'):
            render_command(skill, {'volts_per_div': 12.0})
        self.assertIn('Keep the bench dry.', skill['operator_read'])

    def test_uncited_claims_are_rejected_at_compile_time(self):
        for key in ('parameters', 'warnings', 'commands'):
            bad = fragment()
            bad[key] = [dict(bad[key][0], cite='')]
            with self.assertRaises(ManualSkillError):
                compile_skill(bad)
        bad = fragment(); bad['parameters'][0]['max'] = 0.05
        with self.assertRaises(ManualSkillError):
            compile_skill(bad)

    def test_replay_verifies_commands_against_recorded_trace(self):
        skill = compile_skill(fragment())
        trace = [{'params': {'volts_per_div': 1.0}, 'expected': 'MEAS:CH1:RANGE 1.0V'},
                 {'params': {'volts_per_div': 5.0}, 'expected': 'MEAS:CH1:RANGE 5.0V'},
                 {'params': {'volts_per_div': 2.0}, 'expected': 'MEAS:CH1:RANGE 9.9V'}]
        report = replay(skill, trace)
        self.assertEqual((report['passed'], report['failed']), (2, 1))
        self.assertEqual(report['mismatches'][0]['expected'], 'MEAS:CH1:RANGE 9.9V')
        with self.assertRaises(ManualSkillError):
            replay(skill, [{'params': {'volts_per_div': 99.0}, 'expected': 'x'}])

    def test_fragment_hash_pins_provenance(self):
        a = compile_skill(fragment())['fragment_hash']
        tampered = fragment(); tampered['parameters'][0]['max'] = 9.9
        b = compile_skill(tampered)['fragment_hash']
        self.assertEqual(a, hashlib.sha256(json.dumps(fragment(), sort_keys=True).encode()).hexdigest())
        self.assertNotEqual(a, b)
