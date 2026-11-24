# TV sleep/wake + companion foreground skills — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. (Native-subagent sessions: execute inline, one task at a time, same checkboxes.)

**Goal:** Add three fabric-wide, consent-gated Android skills — `tv_sleep`, `tv_wake`, `companion_foreground` — so the TV obeys invisibly (background relay) and reveals its Companion UI only on explicit owner request from PC/phone/watch.

**Architecture:** PC-side ADB verbs (no companion-app change: the app cannot inject keys or sleep; `RelayService` already survives backgrounded). Each skill follows the exact `screen_capture`/`capture_send` precedent: `ActionDescriptor` + `_impl` with independent `dumpsys` read-back oracle + `RUNNERS` entry + `routing.SKILLS` entry in the Android branch + `composer.SKILL_AUDIENCE` entry (UI-bindable automatically). TDD red→green per skill, then one live TV run with transcript.

**Tech Stack:** Python 3.14 stdlib + unittest (repo suite), ADB shell (`input keyevent`, `am start`, `dumpsys power|activity`), existing `Executor`/consent/journal machinery. No new dependencies.

---

## File map (all paths exact, verified against main @ f52f536)

- Modify `src/adapters/android.py` — add `shell(handle, argv)` after `file_sha256` (strict argv charset, timeout, bounded output; `re`+`subprocess` already imported).
- Modify `src/runtime/primitives.py` — add `import re`, `import time` (after line 8); module helper `_read_wakefulness(android, handle)` after `_s()`; 3 `ActionDescriptor`s after the `capture_montage` entry; 3 `_impl` methods after `_capture_montage`; 3 `RUNNERS` entries on the `'retro_command'` line.
- Modify `src/runtime/routing.py` — 3 `SKILLS` entries after the `capture_send` entry; extend the Android tuple (line 299) with the 3 ids; add tv-only gate for sleep/wake; 3 `_params` lambdas (lines 315–320).
- Modify `src/runtime/composer.py` — 3 `SKILL_AUDIENCE` entries (`'android'`).
- Create `tests/runtime/test_tv_power.py` — all unit tests (mirrors `tests/runtime/test_primitives_media.py`: `ctx()` + fake android + `Executor`).
- Create `dev/tv_sleep_verify.py` — live TV verification run (dev-only, transcript to `E:/shots/tv-sleep-02nov/`).
- Create `docs/evidence/tv-sleep-02nov.md` — live-run evidence note; append runbook section to `docs/jury/DEMO_PHYSICAL_RUNBOOK.md`.

Out of scope (later plans): C screenshot viewer, A watch voice, NL vocab for these skills (button/CLI only), any companion-app change.

## As-built amendments (02-Nov-2026, live TV findings)

1. **Post-send oracle failure → `EXECUTED_UNVERIFIED`, not BLOCKED** (commit `f036ea8`).
   BLOCKED ("refusal before anything was attempted") is false once the keyevent/`am start`
   was sent; follows the `_retro_command` precedent. +3 unit tests (19 total).
2. **Oracle read caps raised** (commit `20f2c8e`). `dumpsys power` = 435 KB on the owner TV,
   `dumpsys activity activities` = 69 KB — both exceeded the 64 KB `shell()` default.
   Oracle reads now pass 1 MB / 4 MB explicit caps; fakes assert the minima.
3. **This TV drops Wi-Fi ADB in sleep** (`offline`, reconnect refused while asleep).
   `tv_sleep` receipt is honestly UNVERIFIED here (effect owner-confirmed); `tv_wake` cannot
   power-on over a dead link — the remote wakes, skills verify after. Runbook §TV-PWR.
4. `dev/tv_sleep_verify.py` accepts an optional skill subset (`argv[2:]`); ctx is the server
   object itself (`Executor(s)`, per `api_v2.executor`).

---

### Task 1: Adapter `shell()` helper (TDD)

**Files:**
- Modify: `src/adapters/android.py` (after `file_sha256`)
- Test: `tests/runtime/test_tv_power.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""TV power + companion foreground skills (SIMULATED_VERIFIED: fake android; no adb calls)."""
import unittest

from src.adapters.android import AndroidAdapter


class RecordingRunner:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, argv, **kw):
        from types import SimpleNamespace
        self.calls.append(argv)
        return SimpleNamespace(stdout=self.stdout, returncode=self.returncode)


class AdapterShell(unittest.TestCase):
    def test_shell_runs_fixed_argv_on_serial(self):
        run = RecordingRunner(stdout="mWakefulness=Asleep\n")
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"192.168.1.15:5555": "h1"}
        out = ad.shell("h1", ("dumpsys", "power"))
        self.assertIn("mWakefulness", out)
        self.assertEqual(run.calls[0][:4], ["adb-stub", "-s", "192.168.1.15:5555", "shell"])

    def test_shell_rejects_metacharacters(self):
        run = RecordingRunner()
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"S1": "h1"}
        with self.assertRaises(ValueError):
            ad.shell("h1", ("input", "keyevent", "A;B"))
        with self.assertRaises(ValueError):
            ad.shell("h1", ("dumpsys",))
        self.assertEqual(run.calls, [])

    def test_shell_raises_on_adb_failure(self):
        run = RecordingRunner(stdout="error: device offline", returncode=1)
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"S1": "h1"}
        with self.assertRaises(ValueError):
            ad.shell("h1", ("dumpsys", "power"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: FAIL with `AttributeError: 'AndroidAdapter' object has no attribute 'shell'` (3 errors, feature missing — not typos).

- [ ] **Step 3: Write minimal implementation**

In `src/adapters/android.py`, after the `file_sha256` method:

```python
    def shell(self, handle, argv, timeout=15, max_bytes=65536):
        """Run one fixed shell argv (callers pass literals only, never user input)."""
        serial = self._serial_for_handle(handle)
        if (not isinstance(argv, (tuple, list)) or not argv or len(argv) > 8
                or any(not isinstance(a, str) or not a or len(a) > 128
                       or not re.fullmatch(r'[A-Za-z0-9_./:=+-]+', a) for a in argv)):
            raise ValueError('bad shell argv')
        result = self.runner([self.executable, '-s', serial, 'shell', *argv], capture_output=True,
                             text=True, encoding='utf-8', errors='replace', timeout=timeout,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or len(result.stdout) > max_bytes:
            raise ValueError('Shell command unavailable')
        return result.stdout
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: `Ran 3 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_tv_power.py src/adapters/android.py
git commit -m "feat(tv-power): bounded AndroidAdapter.shell() for fixed argv"
```

### Task 2: `tv_sleep` skill (TDD)

**Files:**
- Modify: `src/runtime/primitives.py` (imports, `_read_wakefulness`, descriptor, `_tv_sleep`, `RUNNERS`)
- Modify: `src/runtime/routing.py` (`SKILLS`, tuple, tv-gate, `_params`)
- Modify: `src/runtime/composer.py` (`SKILL_AUDIENCE`)
- Test: `tests/runtime/test_tv_power.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/runtime/test_tv_power.py`)

```python
import tempfile
from tests.runtime.test_primitives import ctx
from src.runtime.primitives import Executor


class FakeTVAndroid:
    def __init__(self, power="mWakefulness=Awake\n"):
        self._handles = {"SERIAL1": "h1"}
        self.identity = "id-1"
        self.power = power
        self.shell_calls = []

    def stable_identifier(self, handle, salt):
        return self.identity if handle in self._handles.values() else None

    def shell(self, handle, argv, timeout=15, max_bytes=65536):
        assert handle == "h1"
        self.shell_calls.append(tuple(argv))
        if tuple(argv[:2]) == ("dumpsys", "power"):
            return self.power
        return ""
```

```python
class TvSleep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.c.android = FakeTVAndroid(power="mWakefulness=Asleep\n")
        self.ex = Executor(self.c)

    def test_sleep_executes_and_verifies_asleep(self):
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "EXECUTED")
        self.assertTrue(r["verified"])
        self.assertEqual(self.c.android.shell_calls[0], ("input", "keyevent", "KEYCODE_SLEEP"))
        self.assertEqual(r["result"]["wakefulness"], "Asleep")

    def test_sleep_needs_consent(self):
        r = self.ex.execute("tv_sleep", self.key, {}, False)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("CONSENT_REQUIRED", r["errors"][0])

    def test_sleep_fails_when_still_awake(self):
        self.c.android.power = "mWakefulness=Awake\n"
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "FAILED")

    def test_sleep_fails_when_adb_down(self):
        def dead(handle, argv, timeout=15, max_bytes=65536):
            raise ValueError("Shell command unavailable")
        self.c.android.shell = dead
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "FAILED")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.runtime.test_tv_power.TvSleep -v`
Expected: FAIL — `tv_sleep` unknown to the executor (KeyError/UNKNOWN_PRIMITIVE style failure, not typos).

- [ ] **Step 3: Write minimal implementation**

(a) `src/runtime/primitives.py`: add `import re` and `import time` after line 8 (`import secrets`); add after `_s()`:

```python
def _read_wakefulness(android, handle):
    out = android.shell(handle, ('dumpsys', 'power'))
    m = re.search(r'mWakefulness=(\w+)', out)
    return m.group(1) if m else None
```

(b) Descriptor after the `capture_montage` entry:

```python
    ActionDescriptor('tv_sleep', 'Put an Android TV to sleep (screen off, wakes on remote)',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent for this physical act', 'control grant on a current ADB link'),
                     ('target is a TV', 'identity re-verified'),
                     ('TV asleep; any remote key or tv_wake restores',),
                     'mWakefulness read back Asleep via dumpsys power', 'tv_wake',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'SLEEP_FAILED'), 30, 'single-per-device', True),
```

(c) Implementation after `_capture_montage` (before `_file_pull`):

```python
    def _tv_sleep(self, key, params):
        handle = self._adb_handle(key)
        try:
            self.ctx.android.shell(handle, ('input', 'keyevent', 'KEYCODE_SLEEP'))
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        state = _read_wakefulness(self.ctx.android, handle)
        if state != 'Asleep':
            time.sleep(2)
            try:
                state = _read_wakefulness(self.ctx.android, handle)
            except ValueError as e:
                raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Asleep':
            raise ValueError('SLEEP_FAILED: wakefulness is %s' % state)
        return 'EXECUTED', None, 'TV asleep (mWakefulness=Asleep)', True, {'wakefulness': 'Asleep'}
```

(d) `RUNNERS`: append `'tv_sleep': _tv_sleep,` to the `'retro_command': _retro_command}` line.

(e) `src/runtime/routing.py`: after the `capture_send` `SKILLS` entry:

```python
    'tv_sleep': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': True, 'consent': 'per_invocation', 'targeted': True,
                 'input': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                 'plain': 'Put this TV to sleep now (screen off). Undo: any remote key or tv_wake.'},
```

(f) Extend the Android tuple (line 299) to `('screen_capture', 'file_pull', 'capture_send', 'file_push', 'app_launch', 'capability_probe', 'tv_sleep', 'tv_wake', 'companion_foreground')` and insert right after it:

```python
            if skill_id in ('tv_sleep', 'tv_wake') and d.get('category') != 'tv':
                return out
```

(g) `_params` dict (lines 315–320): add `'tv_sleep': lambda p: {},` (same line style, trailing entries for the next tasks).

(h) `src/runtime/composer.py` `SKILL_AUDIENCE`: add `'tv_sleep': 'android',` after the `'tv_volume_step': 'android',` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: all pass (3 adapter + 4 sleep = 7 tests `OK`).

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_tv_power.py src/runtime/primitives.py src/runtime/routing.py src/runtime/composer.py
git commit -m "feat(tv-power): tv_sleep skill with mWakefulness oracle (TV-only, MANUAL)"
```

### Task 3: `tv_wake` skill (TDD)

Same files as Task 2.

- [ ] **Step 1: Write the failing tests** (append; same `FakeTVAndroid`)

```python
class TvWake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.c.android = FakeTVAndroid(power="mWakefulness=Awake\n")
        self.ex = Executor(self.c)

    def test_wake_executes_and_verifies_awake(self):
        r = self.ex.execute("tv_wake", self.key, {}, True)
        self.assertEqual(r["state"], "EXECUTED")
        self.assertTrue(r["verified"])
        self.assertEqual(self.c.android.shell_calls[0], ("input", "keyevent", "KEYCODE_WAKEUP"))
        self.assertEqual(r["result"]["wakefulness"], "Awake")

    def test_wake_needs_consent(self):
        r = self.ex.execute("tv_wake", self.key, {}, False)
        self.assertEqual(r["state"], "BLOCKED")

    def test_wake_fails_when_still_asleep(self):
        self.c.android.power = "mWakefulness=Asleep\n"
        r = self.ex.execute("tv_wake", self.key, {}, True)
        self.assertEqual(r["state"], "FAILED")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.runtime.test_tv_power.TvWake -v`
Expected: FAIL — `tv_wake` unknown (Tasks 2 tests still pass).

- [ ] **Step 3: Write minimal implementation**

Descriptor (after `tv_sleep`):

```python
    ActionDescriptor('tv_wake', 'Wake an Android TV (screen on)',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent for this physical act', 'control grant on a current ADB link'),
                     ('target is a TV', 'identity re-verified'),
                     ('TV awake',),
                     'mWakefulness read back Awake via dumpsys power', 'tv_sleep',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'WAKE_FAILED'), 30, 'single-per-device', True),
```

Implementation (after `_tv_sleep`):

```python
    def _tv_wake(self, key, params):
        handle = self._adb_handle(key)
        try:
            self.ctx.android.shell(handle, ('input', 'keyevent', 'KEYCODE_WAKEUP'))
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        state = _read_wakefulness(self.ctx.android, handle)
        if state != 'Awake':
            time.sleep(2)
            try:
                state = _read_wakefulness(self.ctx.android, handle)
            except ValueError as e:
                raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Awake':
            raise ValueError('WAKE_FAILED: wakefulness is %s' % state)
        return 'EXECUTED', None, 'TV awake (mWakefulness=Awake)', True, {'wakefulness': 'Awake'}
```

`RUNNERS`: append `'tv_wake': _tv_wake,`. Routing `SKILLS` after `tv_sleep`:

```python
    'tv_wake': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': True, 'consent': 'per_invocation', 'targeted': True,
                'input': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                'plain': 'Wake this TV now (screen on).'},
```

`_params`: add `'tv_wake': lambda p: {},`. Composer: add `'tv_wake': 'android',` after `'tv_sleep'`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: 10 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_tv_power.py src/runtime/primitives.py src/runtime/routing.py src/runtime/composer.py
git commit -m "feat(tv-power): tv_wake skill (inverse of tv_sleep)"
```

### Task 4: `companion_foreground` skill (TDD)

Same files as Task 2.

- [ ] **Step 1: Write the failing tests** (append)

```python
FOCUSED_COMPANION = "mFocusedApp=ActivityRecord{a7ee65e u0 fr.openbridge.companion/.MainActivity t7101}\n"
FOCUSED_OTHER = "mFocusedApp=ActivityRecord{a7ee65e u0 com.google.android.tvlauncher/.MainActivity t7101}\n"


class FakeForegroundAndroid(FakeTVAndroid):
    def __init__(self, power="mWakefulness=Awake\n", activities=FOCUSED_COMPANION):
        super().__init__(power=power)
        self.activities = activities

    def shell(self, handle, argv, timeout=15, max_bytes=65536):
        assert handle == "h1"
        self.shell_calls.append(tuple(argv))
        if tuple(argv[:2]) == ("dumpsys", "power"):
            return self.power
        if tuple(argv[:2]) == ("dumpsys", "activity"):
            return self.activities
        return ""


class CompanionForeground(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.c.android = FakeForegroundAndroid()
        self.ex = Executor(self.c)

    def test_foreground_executes_and_verifies_focus(self):
        r = self.ex.execute("companion_foreground", self.key, {}, True)
        self.assertEqual(r["state"], "EXECUTED")
        self.assertTrue(r["verified"])
        self.assertIn(("am", "start", "-n", "fr.openbridge.companion/.MainActivity"),
                      self.c.android.shell_calls)

    def test_foreground_refuses_when_screen_asleep(self):
        self.c.android.power = "mWakefulness=Asleep\n"
        r = self.ex.execute("companion_foreground", self.key, {}, True)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("DEVICE_ASLEEP", r["errors"][0])

    def test_foreground_fails_when_focus_elsewhere(self):
        self.c.android.activities = FOCUSED_OTHER
        r = self.ex.execute("companion_foreground", self.key, {}, True)
        self.assertEqual(r["state"], "FAILED")

    def test_foreground_needs_consent(self):
        r = self.ex.execute("companion_foreground", self.key, {}, False)
        self.assertEqual(r["state"], "BLOCKED")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.runtime.test_tv_power.CompanionForeground -v`
Expected: FAIL — `companion_foreground` unknown.

- [ ] **Step 3: Write minimal implementation**

Descriptor (after `tv_wake`):

```python
    ActionDescriptor('companion_foreground', 'Bring the OpenBridge Companion app to the foreground',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent (interrupts what is on screen)', 'control grant on a current ADB link'),
                     ('screen awake (tv_wake first if asleep)', 'identity re-verified'),
                     ('Companion activity focused; HOME/remote undoes',),
                     'mFocusedApp names fr.openbridge.companion via dumpsys activity', '',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'DEVICE_ASLEEP', 'FOREGROUND_FAILED'), 30, 'single-per-device', True),
```

Helper (after `_read_wakefulness`):

```python
def _focused_package(android, handle):
    out = android.shell(handle, ('dumpsys', 'activity', 'activities'))
    m = re.search(r'mFocusedApp=ActivityRecord\{[^}]* (\S+)/', out)
    return m.group(1) if m else None
```

Implementation (after `_tv_wake`):

```python
    def _companion_foreground(self, key, params):
        handle = self._adb_handle(key)
        try:
            wake = _read_wakefulness(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if wake != 'Awake':
            raise PrimitiveError('DEVICE_ASLEEP', 'wake the screen first (tv_wake or the remote)')
        try:
            self.ctx.android.shell(handle, ('am', 'start', '-n', 'fr.openbridge.companion/.MainActivity'))
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        time.sleep(2)
        try:
            pkg = _focused_package(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if pkg != 'fr.openbridge.companion':
            raise ValueError('FOREGROUND_FAILED: focused package is %s' % pkg)
        return 'EXECUTED', None, 'Companion focused', True, {'package': pkg}
```

`RUNNERS`: append `'companion_foreground': _companion_foreground,`. Routing `SKILLS` after `tv_wake`:

```python
    'companion_foreground': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': True, 'consent': 'per_invocation', 'targeted': True,
                             'input': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                             'plain': 'Show the Companion app on this screen now. Undo: HOME or the remote.'},
```

`_params`: add `'companion_foreground': lambda p: {},`. Composer: add `'companion_foreground': 'android',` after `'capability_probe': 'android',`. (No tv-only gate: any android target.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: 14 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/runtime/test_tv_power.py src/runtime/primitives.py src/runtime/routing.py src/runtime/composer.py
git commit -m "feat(tv-power): companion_foreground skill with focus oracle"
```

### Task 5: Bindability surface + full suite

**Files:**
- Test: `tests/runtime/test_tv_power.py`

- [ ] **Step 1: Write the failing test** (append)

```python
class BindableSurface(unittest.TestCase):
    def test_new_skills_are_ui_bindable(self):
        from src.runtime.dashboards import BINDABLE_PATCH_SKILLS
        for sid in ("tv_sleep", "tv_wake", "companion_foreground"):
            self.assertIn(sid, BINDABLE_PATCH_SKILLS)

    def test_routing_entries_require_control_consent(self):
        from src.runtime.routing import SKILLS
        for sid in ("tv_sleep", "tv_wake", "companion_foreground"):
            self.assertEqual(SKILLS[sid]["consent"], "per_invocation")
            self.assertTrue(SKILLS[sid]["targeted"])
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m unittest tests.runtime.test_tv_power -v`
Expected: 16 tests `OK` (wiring from Tasks 2–4 already satisfies this; the test locks the surface against regressions).

- [ ] **Step 3: Run the FULL suite**

Run: `python -m unittest discover -s tests -q`
Expected: `Ran 2112 tests ... OK` (2096 + 16 new; exact count asserted from output, never assumed).

- [ ] **Step 4: Commit**

```bash
git add tests/runtime/test_tv_power.py
git commit -m "test(tv-power): lock bindable surface for the 3 new skills"
```

### Task 6: Live TV verification run (real hardware, owner present)

**Files:**
- Create: `dev/tv_sleep_verify.py`
- Output (not in repo): `E:/shots/tv-sleep-02nov/tv-sleep-transcript.json`
- Create: `docs/evidence/tv-sleep-02nov.md`

No unit test for the live run itself (hardware); verification = transcript + oracle reads + owner eyes. The script performs no ADB-injected presses and no pairing: it drives the 3 new skills through the real `Executor` with owner consent.

- [ ] **Step 1: Write the script** (`dev/tv_sleep_verify.py`)

```python
"""Live TV verification: tv_sleep -> oracle -> tv_wake -> oracle -> companion_foreground -> oracle.

Usage: python -m dev.tv_sleep_verify 'android tv'
Resolves the TV serial from discovery, executes the 3 skills with consent=True,
records every receipt + oracle read into E:/shots/tv-sleep-02nov/tv-sleep-transcript.json.
Owner watches the TV go dark, wake, and show the Companion. No presses injected.
"""
import json
import sys
import time
from argparse import Namespace
from pathlib import Path

OUT = Path("E:/shots/tv-sleep-02nov")
OUT.mkdir(parents=True, exist_ok=True)

from src.server import create_server  # noqa: E402
from src.cli import ensure_discovery, default_providers  # noqa: E402

LABEL = sys.argv[1] if len(sys.argv) > 1 else "android tv"
out = {"label": LABEL, "steps": []}


def main():
    s = create_server(0)
    snap = ensure_discovery(s, default_providers(Namespace(providers=None)))
    devs = [d for d in snap.get("devices", []) if d.get("label") == LABEL]
    if not devs:
        raise SystemExit("TV label %r not discovered" % LABEL)
    key = devs[0]["key"]
    from src.runtime.primitives import Executor
    ex = Executor(s.runtime_ctx())
    for skill in ("tv_sleep", "tv_wake", "companion_foreground"):
        r = ex.execute(skill, key, {}, True)
        out["steps"].append({"skill": skill, "state": r["state"],
                             "verified": r.get("verified"), "result": r.get("result"),
                             "errors": r.get("errors")})
        print(skill, "->", r["state"], "verified=%s" % r.get("verified"), flush=True)
        time.sleep(3)
    (OUT / "tv-sleep-transcript.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    if any(s["state"] != "EXECUTED" or not s["verified"] for s in out["steps"]):
        raise SystemExit("LIVE RUN FAILED — see transcript")
    print("LIVE RUN PASS", flush=True)


if __name__ == "__main__":
    main()
```

Note: `s.runtime_ctx()` is illustrative — the worker MUST resolve the real context accessor from `src/server.py` (the object the UI passes to `Executor`) before running; if none exists, construct the documented context the same way `api_v2.skill_invoke` does. The plan fails closed here: do not invent a ctx shape.

- [ ] **Step 2: Run it on the real TV with the owner watching**

Run: `python -m dev.tv_sleep_verify 'android tv'`
Expected: `tv_sleep -> EXECUTED verified=True`, TV dark; `tv_wake -> EXECUTED verified=True`, TV lit; `companion_foreground -> EXECUTED verified=True`, Companion on screen; `LIVE RUN PASS`; transcript JSON written. Owner confirms each visible state.

- [ ] **Step 3: Write the evidence note** (`docs/evidence/tv-sleep-02nov.md`)

Record: date, TV label/serial-suffix, the 3 receipts (state + oracle values + timestamps), transcript path, owner confirmation, and any deviation (e.g. extra wake latency). No footage claim unless the owner records.

- [ ] **Step 4: Commit**

```bash
git add dev/tv_sleep_verify.py docs/evidence/tv-sleep-02nov.md
git commit -m "feat(tv-power): live TV verification run + evidence (sleep/wake/foreground)"
```

### Task 7: Runbook appendix (exact text)

**Files:**
- Modify: `docs/jury/DEMO_PHYSICAL_RUNBOOK.md` (append at end)

- [ ] **Step 1: Append** (no test; docs only)

```markdown
## §TV-PWR — TV sleep/wake + Companion reveal (01/02-Nov-2026)

Owner-visible behavior: the TV obeys while the Companion stays hidden
(`RelayService` foreground service); the UI appears only on explicit
request from PC/phone/watch (skill `companion_foreground`).

1. From any surface, invoke `tv_sleep` on the TV (consent per invocation).
   Oracle: `mWakefulness=Asleep` read back via `dumpsys power`.
2. Invoke `tv_wake`. Oracle: `mWakefulness=Awake`.
3. Invoke `companion_foreground`. Oracle: `mFocusedApp` names
   `fr.openbridge.companion`. Refused with `DEVICE_ASLEEP` if the
   screen is off (wake first). Undone by HOME/the remote.
4. All three skills are one-tap bindable (`BINDABLE_PATCH_SKILLS`);
   demo buttons live on the watch via the standard set_controls flow.
```

- [ ] **Step 2: Commit**

```bash
git add docs/jury/DEMO_PHYSICAL_RUNBOOK.md
git commit -m "docs(tv-power): runbook appendix for sleep/wake/reveal"
```
