import json, unittest
from pathlib import Path
from src.runtime.contract import schema, compatible, CONTRACT_VERSION

GOLDEN=Path(__file__).resolve().parents[2]/'docs'/'coordination'/'contract_v1.schema.json'


class ContractCompatibilityTests(unittest.TestCase):
    def test_current_schema_is_compatible_with_published_golden(self):
        ok,why=compatible(json.loads(GOLDEN.read_text()),schema());self.assertTrue(ok,why)

    def test_removing_or_renaming_a_field_is_rejected(self):
        old=schema();new=json.loads(json.dumps(old));new['types']['CapabilityDescriptor'].remove('reversible')
        self.assertFalse(compatible(old,new)[0])
        new=json.loads(json.dumps(old));new['version']='2.0.0';self.assertFalse(compatible(old,new)[0])
        new=json.loads(json.dumps(old));new['types']['CapabilityDescriptor'].append('new_optional');self.assertTrue(compatible(old,new)[0])

    def test_six_states_are_independent_fields(self):
        f=schema()['types']['CapabilityDescriptor']
        for s in ('discovered','observed','readable','controllable','reversible','verified'):self.assertIn(s,f)
        self.assertTrue(CONTRACT_VERSION.startswith('1.'))
