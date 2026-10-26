"""Versioned Device Fabric contracts. Every value keeps its source, time, verification state and confidence."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import hmac

SCHEMA_VERSION = 1
STATUSES = ('REAL_HARDWARE_VERIFIED', 'INTEGRATION_VERIFIED', 'SIMULATED_VERIFIED', 'IMPLEMENTED_UNVERIFIED', 'NOT_SUPPORTED', 'BLOCKED')
LINK_GRANTS = ('observe', 'read', 'control')          # a link never implies more than it states
IDENTIFIER_KINDS = ('android_serial', 'freebox_uid', 'mac_global', 'mdns_host', 'cast_id', 'hap_id', 'ble_address', 'companion_key', 'upnp_udn')


def now():
    return datetime.now(timezone.utc).isoformat()


def opaque(kind, raw, salt):
    """Stable per-install pseudonym for a raw identifier. Raw serials/MACs never leave the adapter."""
    return kind + ':' + hmac.new(salt, f'{kind}\0{raw}'.encode(), hashlib.sha256).hexdigest()[:24]


def mac_is_randomized(mac):
    """Locally administered bit set => privacy/random MAC: never a strong identity."""
    try:
        return bool(int(mac.split(':')[0], 16) & 0x02)
    except (ValueError, IndexError):
        return True


@dataclass(frozen=True)
class DeviceObservation:
    key: str                  # e.g. 'model', 'battery_percent'
    value: object
    source: str               # 'ADB', 'FREEBOX_API', 'MDNS', 'BLE', 'RELAY:<id>'
    transport: str            # 'USB', 'WIFI', 'LAN', 'BLE', 'INVENTORY'
    observed_at: str
    verified: bool            # read directly from the device (True) vs reported by a third party (False)
    confidence: float = 1.0


@dataclass(frozen=True)
class Identifier:
    kind: str                 # one of IDENTIFIER_KINDS
    value: str                # already opaque
    strong: bool              # only strong identifiers may merge two observations into one device


@dataclass
class Capability:
    name: str                 # 'inspect', 'package_state', 'ble_scan', 'lan_inventory', ...
    level: str                # 'observe' | 'read' | 'write' | 'restore'
    status: str               # one of STATUSES
    via: str                  # route/link that provides it
    evidence: str = ''


@dataclass
class Link:
    parent: str               # device key or 'pc'
    child: str
    transport: str            # 'USB', 'WIFI', 'LAN', 'BLE', 'INVENTORY', 'MDNS'
    grants: tuple             # subset of LINK_GRANTS
    source: str
    observed_at: str = field(default_factory=now)


@dataclass
class ProposedAction:
    device: str
    action: str
    capability: str
    reversible: bool
    restore_method: str
    evidence_refs: tuple


def to_dict(obj):
    return asdict(obj)
