"""Device Capability Contract v1 — shared between the Device Runtime (adapters, policy, journal) and Capability Forge.
Pure data. Changing a field is a breaking change: bump CONTRACT_VERSION and update the golden schema test."""
from dataclasses import dataclass, field, asdict, fields
from enum import Enum

CONTRACT_VERSION = '1.0.0'

VERIFICATION_STATUS = ('REAL_HARDWARE_VERIFIED', 'INTEGRATION_VERIFIED', 'SIMULATED_VERIFIED', 'IMPLEMENTED_UNVERIFIED', 'BLOCKED', 'UNSUPPORTED')


class ReversibilityClass(str, Enum):
    NONE = 'NONE'                    # read-only, nothing to undo
    EXACT = 'EXACT'                  # original value snapshotted and restored bit-exact, then verified
    SESSION_CLEANUP = 'SESSION_CLEANUP'  # OpenBridge-created artefact removed (app, connection, pairing)
    MANUAL = 'MANUAL'                # owner must undo with documented steps
    IRREVERSIBLE = 'IRREVERSIBLE'    # always BLOCKED by policy


@dataclass(frozen=True)
class DeviceIdentity:
    device_key: str                  # graph key, stable for one discovery run
    category: str
    label: str
    strong_identifier_kinds: tuple   # e.g. ('android_serial','mac_global'); values are pseudonymous and never exposed
    possibly_same_as: tuple = ()


@dataclass(frozen=True)
class EvidenceFact:
    device_key: str
    name: str
    value: object
    sources: tuple                   # ('ADB',) / ('FREEBOX_API','MDNS') / ('RELAY:<id>',)
    observed_at: str
    verified: bool                   # read directly from the device vs reported by a third party
    inferred: bool = False           # True only for conclusions computed by OpenBridge
    confidence: float = 1.0


@dataclass(frozen=True)
class DeviceObservation:
    device_key: str
    via_device: str                  # 'pc' or the relay/inventory device key
    transport: str                   # USB | WIFI | EMULATOR | LAN | INVENTORY | BLE
    source: str
    observed_at: str
    rssi: int = None
    stale: bool = False


@dataclass(frozen=True)
class TransportSession:
    device_key: str
    transport: str
    grants: tuple                    # subset of ('observe','read','control')
    authenticated: bool
    opened_by_openbridge: bool       # if True it appears in the session journal


@dataclass(frozen=True)
class RelayRoute:
    target_device: str
    relay_device: str
    relay_id: str
    radio: str                       # 'ble'
    permission_granted: bool
    owner_enabled: bool
    online: bool
    last_success_at: str = None


@dataclass(frozen=True)
class CapabilityPermission:
    name: str                        # e.g. 'android.permission.BLUETOOTH_SCAN', 'freebox:lan', 'owner_consent'
    granted: bool
    obtained_by: str                 # 'android_dialog' | 'freebox_button' | 'adb_prompt' | 'pairing_code' | 'consent' | 'n/a'


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str               # '<device_key>:<name>'
    device_key: str
    name: str
    transport: str
    discovered: bool
    observed: bool
    readable: bool
    controllable: bool
    reversible: bool
    verified: str                    # one of VERIFICATION_STATUS
    permissions: tuple               # CapabilityPermission
    parameters: dict                 # JSON-schema-like description of accepted parameters (empty if read-only)
    operations: tuple                # primitive ids actually supported for this capability
    source: str
    freshness_s: int                 # age of the newest supporting evidence, seconds
    limitations: tuple = ()
    reversibility: str = ReversibilityClass.NONE.value


@dataclass(frozen=True)
class ActionDescriptor:
    primitive_id: str
    title: str
    input_schema: dict
    required_permissions: tuple
    preconditions: tuple
    expected_effects: tuple
    verification: str
    inverse: str                     # primitive id or ''
    reversibility: str
    errors: tuple
    timeout_s: int
    concurrency: str                 # 'single-per-device' | 'single-global' | 'parallel'
    requires_consent: bool


@dataclass(frozen=True)
class TransactionReceipt:
    transaction_id: str
    primitive_id: str
    device_key: str
    state: str                       # PREPARED..REVERTED | QUARANTINED | BLOCKED
    before: object
    after: object
    verified: bool
    started_at: str
    finished_at: str
    errors: tuple = ()


@dataclass(frozen=True)
class RecoveryState:
    pending_transactions: tuple      # transaction ids not REVERTED/closed
    open_session_changes: tuple      # session journal ids
    blocked_reason: str = ''


CONTRACT_TYPES = (DeviceIdentity, EvidenceFact, DeviceObservation, TransportSession, RelayRoute, CapabilityPermission,
                  CapabilityDescriptor, ActionDescriptor, TransactionReceipt, RecoveryState)


def schema():
    """Field names per type: the compatibility surface checked by tests."""
    return {'version': CONTRACT_VERSION, 'types': {t.__name__: [f.name for f in fields(t)] for t in CONTRACT_TYPES},
            'reversibility': [r.value for r in ReversibilityClass], 'verification_status': list(VERIFICATION_STATUS)}


def to_json(obj):
    def conv(v):
        if hasattr(v, '__dataclass_fields__'):
            return {k: conv(x) for k, x in asdict(v).items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, Enum):
            return v.value
        return v
    return conv(obj)


def compatible(old_schema, new_schema):
    """v1 rule: fields may be added, never removed or renamed; enums may only grow; major version must match."""
    if old_schema['version'].split('.')[0] != new_schema['version'].split('.')[0]:
        return False, 'major version changed'
    for t, names in old_schema['types'].items():
        missing = set(names) - set(new_schema['types'].get(t, []))
        if missing:
            return False, f'{t} lost fields {sorted(missing)}'
    for k in ('reversibility', 'verification_status'):
        if set(old_schema[k]) - set(new_schema[k]):
            return False, f'{k} values removed'
    return True, 'compatible'
