"""Hardware -> agent/companion artifact matrix: the right working build per hardware.

Each entry names the file OpenBridge serves over the time-limited LAN portal,
plus the VERIFIED test_ids from docs/DEVICE_EVIDENCE.json that prove the build
family works end to end (a repository test enforces that every cited id is a
VERIFIED registry row). Entries with empty evidence are served as experimental:
the file may be staged, but no hardware proof exists yet, and the UI must say
so. Files resolve under fixed staging directories only; client input selects an
entry id, never a path. Nothing here probes the network.
"""
import hashlib
from pathlib import Path

ARTIFACTS = (
    {'id': 'android-apk', 'label': 'Companion app (Android phone, TV, watch)',
     'os': 'android', 'arch': None, 'filename': 'openbridge-companion.apk', 'source': 'apk',
     'content_type': 'application/vnd.android.package-archive',
     'evidence': ['companion-0.10.0-full-control-cycle', 'companion-0.10.0-tv-launch-pair',
                 'companion-0.10.0-watch-install'],
     'install': ['Open the time-limited link on the device (same Wi-Fi)',
                 'Allow the install when Android asks, then open the app and pair'],
     'run': None},
    {'id': 'windows-x64', 'label': 'Windows agent 64-bit (Windows 10/11)',
     'os': 'windows', 'arch': 'x64', 'filename': 'agent_x64.exe', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': ['pc2-agent-swap-hash-verified'],
     'install': ['On the other PC, open the time-limited link and save the file',
                 'Right-click it and choose "Run as administrator"',
                 'It connects back to this PC with your pre-shared key'],
     'run': 'agent_x64.exe --host {HOST} --port 9876 --token <your-key>'},
    {'id': 'windows-x86-legacy', 'label': 'Windows agent 32-bit legacy (XP SP3 / 7 SP1)',
     'os': 'windows', 'arch': 'x86', 'filename': 'agent-win-x86-legacy.exe', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': ['legacy-agent-xp-vm-proof', 'legacy-agent-win7-vm-proof'],
     'install': ['On the old PC, open the time-limited link and save the file',
                 'Run it as administrator (accept the UAC prompt on Windows 7)',
                 'It connects back to this PC with your pre-shared key'],
     'run': 'agent-win-x86-legacy.exe --host {HOST} --port 9876 --token <your-key>'},
    {'id': 'windows-arm64', 'label': 'Windows agent ARM64',
     'os': 'windows', 'arch': 'arm64', 'filename': 'agent_arm64.exe', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': [],
     'install': ['On the ARM PC, open the time-limited link and save the file',
                 'Run it as administrator with your pre-shared key'],
     'run': 'agent_arm64.exe --host {HOST} --port 9876 --token <your-key>'},
    {'id': 'linux-x64', 'label': 'Linux agent 64-bit',
     'os': 'linux', 'arch': 'x64', 'filename': 'agent-linux-x64', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': [],
     'install': ['On the Linux PC, download the file from the time-limited link',
                 'Make it executable and run it with your pre-shared key'],
     'run': 'chmod +x agent-linux-x64 && ./agent-linux-x64 --host {HOST} --port 9876 --token <your-key>'},
    {'id': 'linux-arm64', 'label': 'Linux agent ARM64 (e.g. Raspberry Pi 4/5)',
     'os': 'linux', 'arch': 'arm64', 'filename': 'agent-linux-arm64', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': [],
     'install': ['On the ARM board, download the file from the time-limited link',
                 'Make it executable and run it with your pre-shared key'],
     'run': 'chmod +x agent-linux-arm64 && ./agent-linux-arm64 --host {HOST} --port 9876 --token <your-key>'},
    {'id': 'esp32-firmware', 'label': 'ESP32 firmware (manual flash)',
     'os': 'esp32', 'arch': None, 'filename': 'openbridge-esp32.bin', 'source': 'agent',
     'content_type': 'application/octet-stream',
     'evidence': [],
     'install': ['Stage openbridge-esp32.bin into the agent folder on this PC',
                 'Flash it with esptool: write_flash 0x10000 openbridge-esp32.bin',
                 'Open the serial monitor to read the pairing prompt, then pair from here'],
     'run': None},
)

ARCH_ALIASES = {'x64': 'x64', 'x86_64': 'x64', 'amd64': 'x64',
                'x86': 'x86', 'i386': 'x86', 'i686': 'x86',
                'arm64': 'arm64', 'aarch64': 'arm64'}


def normalize_arch(raw):
    """Map OS/agent architecture spellings to x64/x86/arm64, else None."""
    if not raw or not isinstance(raw, str):
        return None
    low = raw.strip().lower()
    for prefix in ('x86_64', 'amd64', 'aarch64', 'arm64', 'i686', 'i386', 'x64', 'x86'):
        if low.startswith(prefix):
            return ARCH_ALIASES[prefix]
    return None


def _matches(entry, os_name, arch):
    if entry['os'] != os_name:
        return False
    return entry['arch'] is None or (arch is not None and entry['arch'] == arch)


def resolve(os_name, arch, apk_path, agent_dir):
    """Resolve the artifact for (os, arch): READY only when the file is staged
    AND hardware evidence backs the build family; NEEDS_STEP otherwise."""
    arch = normalize_arch(arch) if arch else None
    entry = next((e for e in ARTIFACTS if _matches(e, os_name, arch)), None)
    if entry is None:
        return None
    base = {k: entry[k] for k in ('id', 'label', 'os', 'arch', 'filename', 'evidence',
                                  'content_type', 'install', 'run')}
    staged = Path(apk_path) if entry['source'] == 'apk' else Path(agent_dir) / entry['filename']
    if not staged.is_file():
        if entry['source'] == 'apk':
            reason = f"{entry['filename']} is not staged on this PC (build it: python -m dev.build_companion)"
        else:
            reason = (f"{entry['filename']} is not staged on this PC (copy it from the BridgeWindows-v4 "
                      f"build into {agent_dir})")
        return base | {'status': 'NEEDS_STEP', 'reason': reason}
    sha = hashlib.sha256(staged.read_bytes()).hexdigest()
    if not entry['evidence']:
        return base | {'status': 'NEEDS_STEP', 'path': str(staged), 'sha256': sha,
                       'reason': f"Experimental build: {entry['filename']} is staged but not yet verified on hardware"}
    return base | {'status': 'READY', 'reason': None, 'path': str(staged), 'sha256': sha}


def matrix_status(apk_path, agent_dir):
    """Resolve every entry (for the hardware picker and the API payload)."""
    return [resolve(e['os'], e['arch'], apk_path, agent_dir) for e in ARTIFACTS]


def detect_platform(key, registry):
    """Derive (os, arch, confidence, evidence) from discovery observations only.

    WINDOWS_AGENT handle -> windows (+ diag architecture when reported).
    ADB handles -> android (the APK is universal, arch stays None).
    Anything else -> unknown: the UI picker asks the owner instead of guessing.
    """
    dev = registry.devices.get(key, {}) if registry else {}
    handles = dev.get('handles', {})
    if 'WINDOWS_AGENT' in handles:
        obs = registry.best_value(key, 'architecture')
        arch = normalize_arch(obs.value) if obs is not None else None
        return ('windows', arch, 'strong', ['agent link (facts read from the device)'])
    if 'USB' in handles or 'WIFI' in handles:
        return ('android', None, 'strong', ['ADB link'])
    return (None, None, 'unknown', [])
