"""MI v3: gate synonym coverage + one bounded param repair.

Root-caused from MI-COMP dev failures:
- 'Smartwatch' was missing from the gate's watch synonyms, so a
  correctly targeted app_launch clarified as TARGET_UNRELATED.
- The model emits integers as JSON strings ('30'); the skill
  schemas demand integers. One deterministic coercion
  (numeric-string -> int, schema-directed, value-preserving)
  repairs it; anything else still refuses.
"""
import unittest


class ReadyRouter:
    def skill_routes(self, skill, key):
        return {'selected_route_id': 'rt', 'routes': [
            {'route_id': 'rt', 'state': 'READY',
             'hops': [{'transport': 'STUB', 'primitive_id': 'read_facts'}],
             'operation_id': 'op', 'evidence': 'stub'}], 'selection': {}}


def _devices():
    return [{'key': 'dev-w', 'label': 'Smartwatch', 'category': 'watch',
             'handles': {'USB': 'h'}},
            {'key': 'dev-tv', 'label': 'Android TV', 'category': 'tv',
             'handles': {'WIFI': 'h2'}}]


class Synonyms(unittest.TestCase):
    def test_smartwatch_target_passes_gate(self):
        from src.runtime import composer as comp
        proposer = lambda p: {'model_id': 's', 'endpoint': 's', 'content':
            '{"steps": [{"skill_id": "app_launch", "target": "Smartwatch",'
            ' "params": {"package": "com.store"}}]}'}
        out = comp.propose_and_compose('Open the Play Store on the watch.',
                                       _devices(), ReadyRouter(), proposer)
        self.assertEqual(out['steps'][0]['status'], 'allowed')


class IntRepair(unittest.TestCase):
    def test_numeric_string_coerced(self):
        from src.runtime.composer import coerce_params
        schema = {'type': 'object', 'properties': {'seconds': {'type': 'integer'}}}
        self.assertEqual(coerce_params(schema, {'seconds': '30'}), {'seconds': 30})

    def test_non_numeric_left_alone(self):
        from src.runtime.composer import coerce_params
        schema = {'type': 'object', 'properties': {'seconds': {'type': 'integer'}}}
        self.assertEqual(coerce_params(schema, {'seconds': 'soon'}), {'seconds': 'soon'})
        self.assertEqual(coerce_params(schema, {'seconds': '3.5'}), {'seconds': '3.5'})
        self.assertEqual(coerce_params(schema, {'seconds': True}), {'seconds': True})
        self.assertEqual(coerce_params(schema, {'seconds': 30}), {'seconds': 30})

    def test_compose_allows_repaired_step(self):
        from src.runtime import composer as comp
        proposer = lambda p: {'model_id': 's', 'endpoint': 's', 'content':
            '{"steps": [{"skill_id": "ble_scan_room", "target": "fabric",'
            ' "params": {"seconds": "10"}}]}'}
        out = comp.propose_and_compose('Scan the room for Bluetooth devices.',
                                       _devices(), ReadyRouter(), proposer)
        self.assertEqual(out['steps'][0]['status'], 'allowed')
        self.assertEqual(out['steps'][0]['params'], {'seconds': 10})


if __name__ == '__main__':
    unittest.main(verbosity=2)
