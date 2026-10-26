"""Deterministic inspection; no inference or hardware action."""
from src.adapters.simulated import discover


def authorize(action):
    return 'ALLOW' if action == 'inspect' else 'DENY'


def inspect_device(device_id):
    device = next((item for item in discover() if item['id'] == device_id), None)
    if device is None:
        raise ValueError('Unknown device')
    return {
        'device_id': device_id, 'status': 'READ_ONLY', 'simulated': True,
        'model_status': 'NOT_CONNECTED', 'observed_at': device['observed_at'],
        'summary': 'Fixture inspected. Hardware changes are unavailable in this phase.',
        'evidence': [
            {'key': key, 'value': value, 'source': 'SIMULATED', 'observed_at': device['observed_at']}
            for key, value in device['facts'].items()
        ],
        'checks': [
            {'name': 'Source identified', 'status': 'PASS', 'detail': 'Synthetic fixture; no real device connected.'},
            {'name': 'Write permission', 'status': 'BLOCKED', 'detail': 'This release permits inspection only.'},
            {'name': 'Meta inference', 'status': 'NOT_TESTED', 'detail': 'No runtime model is connected.'},
            {'name': 'Physical rollback', 'status': 'NOT_TESTED', 'detail': 'No physical transaction was attempted.'},
        ],
    }
