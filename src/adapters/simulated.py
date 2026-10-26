"""Synthetic fixture only. Does not inspect or change a physical device."""
from datetime import datetime, timezone


def discover():
    return [{
        'id': 'demo-android', 'name': 'Android lab device',
        'platform': 'Android 15', 'transport': 'Fixture',
        'source': 'SIMULATED', 'simulated': True,
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'facts': {'battery_percent': 72, 'storage_free_gb': 38, 'screen_timeout_seconds': 30},
        'capabilities': ['inspect'],
    }]
