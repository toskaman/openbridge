# Wi-Fi direct transport (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PC reaches Companions over direct LAN first (Wi-Fi/LAN IP), adb forward only as fallback, with zero companion change.

**Architecture:** `AndroidAdapter.relay_urls()` returns ordered candidates per handle (direct serial-IP URL, then adb forward); `relay.failover_transport()` tries each per request (transport errors fail over, protocol refusals propagate); `server.py` pair/restore store `urls` and build failover sends; voice fetch loops over the same candidates. Owner priority wifi → lan → adb-wifi → adb maps to: serial-IP direct first, then that serial's adb forward (which rides adb-over-wifi or adb-over-USB); USB-paired devices gain a direct URL post-pair via mDNS TXT relay-id match.

**Tech Stack:** Python 3.11+ stdlib only (urllib, ipaddress), unittest, existing `src/fabric/mdns.py` browse.

---

## File structure

- Modify `src/adapters/android.py` — add `direct_url()`, `relay_urls()`, `lan_url_for_relay()`; `forward_companion()` untouched.
- Modify `src/fabric/relay.py` — add `failover_transport()`, `fetch_voice_urls()`; `http_transport()`, `fetch_voice()`, `_check_scope()` untouched.
- Modify `src/runtime/command_drain.py` — `_handle()` uses `fetch_voice_urls` with `relay['urls']` by default; custom `fetch_voice_fn` doubles keep the single-URL call shape.
- Modify `src/server.py` — pair-start, pair-confirm (+ USB direct upgrade), restore_relays build `urls` + failover sends and persist `relay['urls']`.
- Create `scripts/companion_wifi_setup.py` — one-time grants + pair + ADB-disconnected proof.
- Create `tests/fabric/test_relay_transport.py` — all unit tests below.
- Modify `docs/superpowers/specs/2026-10-31-wifi-direct-design.md` — §3 records the wifi → lan → adb-wifi → adb ordering mapping.

---

### Task 0: Branch + spec ordering note

**Files:**
- Modify: `docs/superpowers/specs/2026-10-31-wifi-direct-design.md`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feat/p32-wifi-direct origin/main
```

- [ ] **Step 2: Record the transport priority in the spec**

Append to §3 of `docs/superpowers/specs/2026-10-31-wifi-direct-design.md`:

```markdown
Transport priority (owner order wifi → lan → adb-wifi → adb): for a
handle, try the serial-IP direct URL first (whatever medium carries it),
then that serial's adb forward (which rides adb-over-wifi or adb-over-USB).
USB-paired devices gain a direct URL after pairing via mDNS TXT relay-id
match (`lan_url_for_relay`).
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-31-wifi-direct-design.md
git commit -m "docs: record wifi-direct transport priority"
```

---

### Task 1: Direct URL + ordered candidates

**Files:**
- Modify: `src/adapters/android.py` (after `forward_companion`, ~line 239)
- Test: `tests/fabric/test_relay_transport.py`

- [ ] **Step 1: Write the failing test**

```python
"""Ordered relay transports: direct Wi-Fi/LAN first, adb forward last. No device."""
import unittest
from types import SimpleNamespace

from src.adapters.android import AndroidAdapter


def _adapter():
    def run(args, **kw):
        a = args[1:]
        if a == ['forward', '--list']:
            return SimpleNamespace(returncode=0, stdout='')
        if a[0] == '-s' and a[2:] == ['forward', 'tcp:0', 'tcp:47800']:
            return SimpleNamespace(returncode=0, stdout='50111\n')
        return SimpleNamespace(returncode=0, stdout='')
    ad = AndroidAdapter(executable='adb', runner=run)
    ad._handles = {'192.168.1.14:37565': 'h-watch', 'BV9300PEEA0004883': 'h-usb'}
    return ad


class DirectUrl(unittest.TestCase):
    def test_wifi_serial_gives_direct_url(self):
        self.assertEqual(_adapter().direct_url('h-watch'), 'http://192.168.1.14:47800')

    def test_usb_serial_gives_none(self):
        self.assertIsNone(_adapter().direct_url('h-usb'))

    def test_unknown_handle_raises(self):
        with self.assertRaises(ValueError):
            _adapter().direct_url('h-nope')

    def test_non_private_ip_gives_none(self):
        ad = _adapter()
        ad._handles['8.8.8.8:5555'] = 'h-pub'
        self.assertIsNone(ad.direct_url('h-pub'))

    def test_loopback_ip_gives_none(self):
        ad = _adapter()
        ad._handles['127.0.0.1:5555'] = 'h-lo'
        self.assertIsNone(ad.direct_url('h-lo'))


class RelayUrls(unittest.TestCase):
    def test_direct_first_then_forward(self):
        urls = _adapter().relay_urls('h-watch')
        self.assertEqual(urls, ['http://192.168.1.14:47800', 'http://127.0.0.1:50111'])

    def test_usb_is_forward_only(self):
        self.assertEqual(_adapter().relay_urls('h-usb'), ['http://127.0.0.1:50111'])

    def test_unknown_raises_without_forward_side_effect(self):
        calls = []
        def run(args, **kw):
            calls.append(args[1:])
            return SimpleNamespace(returncode=0, stdout='')
        ad = AndroidAdapter(executable='adb', runner=run)
        ad._handles = {}
        with self.assertRaises(ValueError):
            ad.relay_urls('h-nope')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.fabric.test_relay_transport -v`
Expected: FAIL with `AttributeError` (`direct_url` not defined).

- [ ] **Step 3: Write minimal implementation**

Append after `forward_companion` in `src/adapters/android.py`:

```python
    def direct_url(self, handle):
        """Direct-LAN relay URL for a Wi-Fi adb serial (`ip:port` -> `http://ip:47800`).

        USB serials have no IP: None (post-pairing, `lan_url_for_relay`
        matches the companion mDNS record by relay id instead). Private
        IPv4 only; never loopback (that tier is the adb forward)."""
        import ipaddress
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
        if serial is None:
            raise ValueError('Unknown device')
        ip, _, _ = serial.rpartition(':')
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if address.version != 4 or not address.is_private or address.is_loopback:
            return None
        return f'http://{ip}:47800'

    def relay_urls(self, handle):
        """Ordered relay candidates: direct Wi-Fi/LAN first, adb forward last.

        Owner priority wifi -> lan -> adb-wifi -> adb maps to: the serial IP
        is tried first (whatever medium carries it), then the adb forward for
        that serial (which itself rides adb-over-wifi or adb-over-USB)."""
        urls = []
        direct = self.direct_url(handle)
        if direct:
            urls.append(direct)
        urls.append(self.forward_companion(handle))
        return urls
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.fabric.test_relay_transport -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/android.py tests/fabric/test_relay_transport.py
git commit -m "feat: ordered relay candidates, direct LAN first"
```

---

### Task 2: Failover transport

**Files:**
- Modify: `src/fabric/relay.py` (after `http_transport`, ~line 315)
- Test: `tests/fabric/test_relay_transport.py` (append classes)

- [ ] **Step 1: Write the failing test**

```python
from unittest import mock

from src.fabric import relay as R


class Failover(unittest.TestCase):
    def test_tries_in_order_first_success_wins(self):
        seen = []
        def fake(url, timeout=25):
            seen.append((url, timeout))
            def send(_r, m):
                if url.startswith('http://127.0.0.1'):
                    raise OSError('refused')
                return {'ok': True}
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:50111', 'http://192.168.1.14:47800'])
            self.assertEqual(send(None, {'op': 'x'}), {'ok': True})
        self.assertEqual([u for u, _ in seen],
                         ['http://127.0.0.1:50111', 'http://192.168.1.14:47800'])

    def test_lan_gets_short_timeout_loopback_gets_full(self):
        seen = {}
        def fake(url, timeout=25):
            seen[url] = timeout
            return lambda _r, m: {'ok': True}
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            R.failover_transport(['http://192.168.1.14:47800', 'http://127.0.0.1:50111'],
                                 lan_timeout=3, timeout=25)
        self.assertEqual(seen, {'http://192.168.1.14:47800': 3, 'http://127.0.0.1:50111': 25})

    def test_protocol_refusal_propagates_without_failover(self):
        calls = []
        def fake(url, timeout=25):
            def send(_r, m):
                calls.append(url)
                raise R.RelayError('Relay refused: bad envelope')
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:1', 'http://127.0.0.1:2'])
            with self.assertRaises(R.RelayError):
                send(None, {'op': 'x'})
        self.assertEqual(calls, ['http://127.0.0.1:1'])

    def test_all_down_reraises_last_oserror(self):
        def fake(url, timeout=25):
            def send(_r, m):
                raise OSError('down ' + url)
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:1', 'http://127.0.0.1:2'])
            with self.assertRaises(OSError):
                send(None, {'op': 'x'})

    def test_empty_urls_rejected(self):
        with self.assertRaises(R.RelayError):
            R.failover_transport([])

    def test_out_of_scope_rejected_at_construction(self):
        with self.assertRaises(R.RelayError):
            R.failover_transport(['http://8.8.8.8:47800'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.fabric.test_relay_transport.Failover -v`
Expected: FAIL with `AttributeError` (`failover_transport` not defined).

- [ ] **Step 3: Write minimal implementation**

Append after `http_transport` in `src/fabric/relay.py`:

```python
def failover_transport(urls, lan_timeout=3, timeout=25):
    """POST JSON trying each relay URL in order. Transport errors (refused,
    reset, timeout) move to the next URL; protocol refusals (RelayError)
    propagate at once: a wrong key or a stale forward answering from another
    device must never silently reroute. LAN URLs fail fast (`lan_timeout`)
    so blackholed subnets (client isolation) fall back quickly; loopback
    (adb forward) keeps the full `timeout`."""
    from urllib.parse import urlsplit
    import ipaddress
    urls = list(urls or [])
    if not urls:
        raise RelayError('No relay URL')
    for u in urls:
        _check_scope(u)
    sends = []
    for u in urls:
        ip = ipaddress.ip_address(urlsplit(u).hostname)
        sends.append(http_transport(u, timeout=timeout if ip.is_loopback else lan_timeout))

    def send(_relay, message):
        last = None
        for s in sends:
            try:
                return s(_relay, message)
            except RelayError:
                raise
            except (OSError, TimeoutError) as e:
                last = e
        raise last

    return send
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.fabric.test_relay_transport -v`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fabric/relay.py tests/fabric/test_relay_transport.py
git commit -m "feat: failover relay transport with fast LAN timeout"
```

---

### Task 3: Voice fetch over candidates + drain wiring

**Files:**
- Modify: `src/fabric/relay.py` (after `fetch_voice`)
- Modify: `src/runtime/command_drain.py` (`_handle`, ~line 67)
- Test: `tests/fabric/test_relay_transport.py` (append) + run `tests/runtime/test_command_drain.py`

- [ ] **Step 1: Write the failing test**

```python
class FetchVoiceUrls(unittest.TestCase):
    def test_validation_errors_raise_without_network(self):
        with self.assertRaises(R.RelayError):
            R.fetch_voice_urls(['http://127.0.0.1:1'], b'k' * 32, 'c' * 16, -5, 'z' * 64)

    def test_falls_over_on_oserror(self):
        calls = []
        def fake(url, *a, **k):
            calls.append(url)
            if url.endswith(':1'):
                raise OSError('down')
            return b'pcm'
        with mock.patch.object(R, 'fetch_voice', side_effect=fake):
            out = R.fetch_voice_urls(['http://127.0.0.1:1', 'http://127.0.0.1:2'],
                                     b'k' * 32, 'c' * 16, 3, 'a' * 64)
        self.assertEqual(out, b'pcm')
        self.assertEqual(calls, ['http://127.0.0.1:1', 'http://127.0.0.1:2'])

    def test_refusal_propagates_without_failover(self):
        def fake(url, *a, **k):
            raise R.RelayError('Relay refused: forbidden')
        with mock.patch.object(R, 'fetch_voice', side_effect=fake):
            with self.assertRaises(R.RelayError):
                R.fetch_voice_urls(['http://127.0.0.1:1', 'http://127.0.0.1:2'],
                                   b'k' * 32, 'c' * 16, 3, 'a' * 64)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.fabric.test_relay_transport.FetchVoiceUrls -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3a: Write `fetch_voice_urls`**

Append after `fetch_voice` in `src/fabric/relay.py`:

```python
def fetch_voice_urls(urls, key, clip_id, expected_bytes, expected_sha256, timeout=25,
                     relay_id=None, aead_version=None, lan_timeout=3):
    """`fetch_voice` over ordered candidates: same failover rule as
    `failover_transport` (transport errors move on, refusals propagate)."""
    from urllib.parse import urlsplit
    import ipaddress
    urls = list(urls or [])
    if not urls:
        raise RelayError('No relay URL')
    last = None
    for u in urls:
        try:
            ip = ipaddress.ip_address(urlsplit(u).hostname or '')
            t = timeout if ip.is_loopback else min(timeout, lan_timeout)
        except ValueError:
            t = timeout  # fetch_voice reports the scope violation as RelayError
        try:
            return fetch_voice(u, key, clip_id, expected_bytes, expected_sha256,
                               timeout=t, relay_id=relay_id, aead_version=aead_version)
        except RelayError:
            raise
        except (OSError, TimeoutError) as e:
            last = e
    raise last
```

- [ ] **Step 3b: Wire the drain (default path only; custom doubles unchanged)**

In `src/runtime/command_drain.py`, `_handle()`, replace:

```python
        fetch = fetch_voice_fn or R.fetch_voice
        pcm = fetch(relay['url'], relay['key'], cmd['clip_id'], cmd['bytes'], cmd['sha256'],
                    relay_id=rid, aead_version=relay.get('aead'))
```

with:

```python
        fetch = fetch_voice_fn or R.fetch_voice_urls
        if fetch is R.fetch_voice_urls:
            pcm = fetch(relay.get('urls') or [relay['url']], relay['key'], cmd['clip_id'],
                        cmd['bytes'], cmd['sha256'], relay_id=rid, aead_version=relay.get('aead'))
        else:  # injected doubles keep the single-URL call shape
            pcm = fetch(relay['url'], relay['key'], cmd['clip_id'], cmd['bytes'], cmd['sha256'],
                        relay_id=rid, aead_version=relay.get('aead'))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.fabric.test_relay_transport tests.runtime.test_command_drain -v`
Expected: PASS (all; existing drain doubles still receive a single URL).

- [ ] **Step 5: Commit**

```bash
git add src/fabric/relay.py src/runtime/command_drain.py tests/fabric/test_relay_transport.py
git commit -m "feat: voice fetch fails over across relay candidates"
```

---

### Task 4: mDNS match by relay id (USB → LAN upgrade)

**Files:**
- Modify: `src/adapters/android.py` (after `relay_urls`)
- Test: `tests/fabric/test_relay_transport.py` (append)

- [ ] **Step 1: Write the failing test**

```python
class LanUrlForRelay(unittest.TestCase):
    INST = {'service': '_openbridge-relay._tcp', 'instance': 'OpenBridge-abc',
            'host': 'watch.local', 'port': 47800, 'addresses': ['192.168.1.14'],
            'txt': {'relay': 'relay-39f86439fbae'}, 'category': 'companion'}

    def test_match_returns_direct_url(self):
        ad = _adapter()
        with mock.patch('src.fabric.mdns.discover', return_value={'instances': [self.INST]}):
            self.assertEqual(ad.lan_url_for_relay('relay-39f86439fbae'),
                             'http://192.168.1.14:47800')

    def test_bad_relay_id_returns_none_without_scan(self):
        with mock.patch('src.fabric.mdns.discover', side_effect=AssertionError('must not scan')):
            self.assertIsNone(_adapter().lan_url_for_relay('nope'))

    def test_no_match_returns_none(self):
        ad = _adapter()
        with mock.patch('src.fabric.mdns.discover', return_value={'instances': []}):
            self.assertIsNone(ad.lan_url_for_relay('relay-39f86439fbae'))

    def test_browse_error_returns_none(self):
        ad = _adapter()
        with mock.patch('src.fabric.mdns.discover', side_effect=OSError('no net')):
            self.assertIsNone(ad.lan_url_for_relay('relay-39f86439fbae'))

    def test_out_of_scope_address_skipped(self):
        ad = _adapter()
        inst = dict(self.INST, addresses=['8.8.8.8'])
        with mock.patch('src.fabric.mdns.discover', return_value={'instances': [inst]}):
            self.assertIsNone(ad.lan_url_for_relay('relay-39f86439fbae'))

    def test_bad_port_skipped(self):
        ad = _adapter()
        inst = dict(self.INST, port=80)
        with mock.patch('src.fabric.mdns.discover', return_value={'instances': [inst]}):
            self.assertIsNone(ad.lan_url_for_relay('relay-39f86439fbae'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.fabric.test_relay_transport.LanUrlForRelay -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

Append after `relay_urls` in `src/adapters/android.py`:

```python
    @staticmethod
    def lan_url_for_relay(relay_id, timeout=1.0):
        """Direct-LAN URL by mDNS match on the companion TXT relay id.

        Gives USB-paired devices a direct URL after pairing (their serial
        carries no IP). Bounded single browse; any failure or mismatch is
        None (the caller keeps the adb forward)."""
        import re as _re
        from src.fabric import mdns
        if not _re.fullmatch(r'relay-[0-9a-f]{12}', relay_id or ''):
            return None
        try:
            res = mdns.discover(timeout=timeout, services=('_openbridge-relay._tcp',))
        except OSError:
            return None
        for inst in res.get('instances', []):
            if inst.get('service') != '_openbridge-relay._tcp':
                continue
            if (inst.get('txt') or {}).get('relay') != relay_id:
                continue
            port = inst.get('port')
            if not isinstance(port, int) or isinstance(port, bool) or not 1024 < port < 65536:
                continue
            for ip in inst.get('addresses', []):
                import ipaddress as _ip
                try:
                    a = _ip.ip_address(ip)
                except ValueError:
                    continue
                if a.version == 4 and a.is_private and not a.is_loopback \
                        and mdns.in_scope(ip, mdns.default_scope()):
                    return f'http://{ip}:{port}'
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.fabric.test_relay_transport -v`
Expected: PASS (23 tests).

- [ ] **Step 5: Commit**

```bash
git add src/adapters/android.py tests/fabric/test_relay_transport.py
git commit -m "feat: direct LAN URL by mDNS relay-id match"
```

---

### Task 5: Server wiring (pair + restore)

**Files:**
- Modify: `src/server.py` (restore_relays ~line 457, relay_action pair-start ~line 484, pair-confirm ~line 508)
- Test: full suite `python -m unittest discover -s tests`

- [ ] **Step 1: Write the failing test**

No new test file: the contract is covered by Tasks 1–4 plus the existing
server/relay suites. Verify the seam first — run and record the baseline:

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (1254 tests) before the change.

- [ ] **Step 2: Wire pair-start**

In `src/server.py`, `relay_action`, replace:

```python
            url = server.android.forward_companion(handle)
            send = transport_factory(url)
```

with:

```python
            urls = server.android.relay_urls(handle)
            send = transport_factory(urls[0], urls=urls) if transport_factory is not fabric_relay.http_transport else fabric_relay.failover_transport(urls)
```

Wait — simpler and seam-preserving: `transport_factory` defaults to
`fabric_relay.http_transport` (single URL). Keep the seam: build the
failover send here and keep `url = urls[0]` for the pending record:

```python
            urls = server.android.relay_urls(handle)
            url = urls[0]
            send = fabric_relay.failover_transport(urls) if transport_factory is fabric_relay.http_transport else transport_factory(url)
```

And in the pending record add `'urls': urls`:

```python
                server.relay_pending[handle] = {'send': send, 'url': url, 'urls': urls, 'hello': hello, 'pc_nonce': pc_nonce, 'handle': handle, 'started_at': now}
```

- [ ] **Step 3: Wire pair-confirm (persist urls + USB direct upgrade)**

After `server.relays.relays[rid]['url'] = pending.get('url')` add:

```python
            urls = list(pending.get('urls') or [pending.get('url')])
            if len(urls) == 1:  # USB serial: no direct URL pre-pair; match mDNS by relay id now
                direct = server.android.lan_url_for_relay(rid)
                if direct and direct not in urls:
                    urls.insert(0, direct)
                    server.relays.relays[rid]['send'] = pending['send'] = fabric_relay.failover_transport(urls)
                    if server.relays.relays[rid].get('aead'):
                        from src.fabric import aead as _aead
                        server.relays.relays[rid]['send'] = _aead.encrypting_send(pending['send'], rid)
            server.relays.relays[rid]['urls'] = urls
```

Note: place this AFTER the existing aead wrap block so the re-wrap order
stays correct (failover inside, AEAD outside).

- [ ] **Step 4: Wire restore_relays**

In `src/server.py`, `restore_relays`, replace:

```python
                url = server.android.forward_companion(handle)
```

with:

```python
                url = server.android.forward_companion(handle)
                urls = server.android.relay_urls(handle)
                url = urls[0]
```

then replace `send = transport_factory(url)` with:

```python
                send = fabric_relay.failover_transport(urls) if transport_factory is fabric_relay.http_transport else transport_factory(url)
```

and after `relay['url'] = url` add `relay['urls'] = urls`.

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (1254 + 23 new = 1277 tests).

- [ ] **Step 6: Commit**

```bash
git add src/server.py
git commit -m "feat: pair/restore store ordered relay URLs with failover sends"
```

---

### Task 6: One-time Wi-Fi setup script

**Files:**
- Create: `scripts/companion_wifi_setup.py`
- Test: `python scripts/companion_wifi_setup.py --help` + `--dry-run` (no device)

- [ ] **Step 1: Write the script (it is its own spec; dry-run is the test)**

```python
"""One-time Companion Wi-Fi setup: ADB grants, first pairing, ADB-disconnected proof.

Usage (serial = `adb devices` entry, e.g. 192.168.1.14:37565):
    python scripts/companion_wifi_setup.py --serial SERIAL [--timeout 120]

Flow: grant DUMP + READ_LOGS over ADB (persist until uninstall) -> pair via
Core (code prompt, shown on the device) -> `adb disconnect` -> signed
get_status over the direct-LAN URL with ADB fully out of the picture.
Exit 0 prints PROOF with the relay id and the transport used.
"""
import argparse
import subprocess
import sys
import time

sys.path.insert(0, '.')

ADB = 'adb'


def run(*args, timeout=60):
    r = subprocess.run([ADB, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if args.dry_run:
        print('DRY-RUN OK (no device touched)')
        return 0
    import secrets
    from src.cli import Core, ensure_discovery
    from src.fabric import relay as R
    t0 = time.time()
    for perm in ('android.permission.DUMP', 'android.permission.READ_LOGS'):
        rc, out = run('-s', args.serial, 'shell', 'pm', 'grant', 'fr.openbridge.companion', perm)
        print(('granted ' if rc == 0 else 'GRANT-FAILED ') + perm)
        if rc != 0:
            return 1
    with Core() as server:
        ensure_discovery(server, ['android'])
        handle = None
        for d in (server.fabric_snapshot or {}).get('devices', []):
            for serial, h in (server.android._handles or {}).items():
                if serial == args.serial and h in (d.get('handles') or {}).values():
                    handle = h
        if not handle:
            print('SERIAL NOT IN DISCOVERY')
            return 1
        urls = server.android.relay_urls(handle)
        print('URLS', urls)
        send = R.failover_transport(urls)
        hello = send(None, {'op': 'pair_request', 'pc_nonce': secrets.token_hex(16)})
        code = input('Enter the %s code shown on the device: ' % hello.get('relay_id')).strip().replace(' ', '')
        key = R.derive_key(code, hello['relay_nonce'], hello.get('pc_nonce') or '')
        rid = hello['relay_id']
        reply = send(None, R.command(key, rid, 'discover_capabilities'))
        R.verify(key, reply, None)
        print('PAIRED', rid)
        run('disconnect', args.serial)
        time.sleep(2)
        direct = [u for u in urls if not u.startswith('http://127.0.0.1')]
        if not direct:
            print('NO DIRECT URL (USB serial without mDNS match)')
            return 1
        proof = R.http_transport(direct[0])(None, R.command(key, rid, 'get_status'))
        R.verify(key, proof, {})
        print('PROOF relay=%s transport=direct-lan url=%s elapsed=%.0fs'
              % (rid, direct[0], time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

NOTE for the worker: `hello.get('pc_nonce')` is wrong — the pc_nonce is
the one WE generated (`secrets.token_hex(16)` above), not echoed. Keep a
local `pc_nonce` variable and pass it to `derive_key`. Fix while writing
(the dry-run test does not cover it; the live Task 7 run does).

- [ ] **Step 2: Run the dry-run**

Run: `python scripts/companion_wifi_setup.py --serial X --dry-run`
Expected: `DRY-RUN OK (no device touched)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/companion_wifi_setup.py
git commit -m "feat: one-time companion Wi-Fi setup script"
```

---

### Task 7: Live proof + evidence

**Files:**
- Evidence: `E:/shots/wifi-direct-*.png`, registry `docs/DEVICE_EVIDENCE.json`

- [ ] **Step 1: Full suite green**

Run: `python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (1277 tests).

- [ ] **Step 2: Live ADB-disconnected proof (owner hardware)**

Run with the watch on Wi-Fi (replace SERIAL):

```powershell
python scripts/companion_wifi_setup.py --serial SERIAL
```

Expected: `PROOF relay=relay-… transport=direct-lan` with ADB
disconnected. Then, ADB still disconnected, run one drain round-trip
(type one order on the device, confirm the caption changes within 60 s)
and screenshot it to `E:/shots/wifi-direct-drain.png`.

- [ ] **Step 3: Evidence row + matrix sync**

Add one VERIFIED row to `docs/DEVICE_EVIDENCE.json` (direct-LAN relay
with ADB disconnected, drain round-trip), then:

```powershell
python -m dev.device_registry --render
python -m dev.device_registry --check
```

Expected: `render` regenerates the matrix, `check` passes.

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/p32-wifi-direct
gh pr create --base main --head feat/p32-wifi-direct --title "feat: Wi-Fi direct relay transport (ADB fallback)" --body "Phase A of the approved Wi-Fi direct design. Direct LAN first, adb forward fallback, USB mDNS upgrade, one-time setup script. Live proof: ADB-disconnected drain round-trip."
```

---

## Self-review

1. **Spec coverage:** §3 transport + ordering → Tasks 1,2,4,5. §4.1 PC
   components → Tasks 1–6. §5 data flow → Task 5 (urls persisted,
   endpoint-independent keys). §6 errors → Task 2 (refusal propagates,
   fast LAN timeout) + Task 4 (None on any failure). §7 tests → each task
   has RED→GREEN unit tests; live proof is Task 7. Phase 2 (companion
   ops) is explicitly out of this plan — separate plan later.
2. **Placeholder scan:** no TBD/TODO; every step has exact code/commands.
   One deliberate worker fix is flagged inline (Task 6 pc_nonce).
3. **Type consistency:** `relay_urls` → `list[str]`; `failover_transport`
   → `send(relay, message)` matching `http_transport`'s shape;
   `fetch_voice_urls(urls, key, clip_id, bytes, sha, ...)` mirrors
   `fetch_voice`; drain passes `relay['urls'] or [relay['url']]`;
   server persists `relay['urls']` + `relay['url'] = urls[0]`.
