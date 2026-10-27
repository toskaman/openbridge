"""Seeded 1-click signature demo (SIMULATED): grounded bind + skill compile + MCP read path.

Deterministic doubles only: loopback challenge adapter, fixture manual fragment,
in-process server. No camera, no Companion channel, no model calls. Prints a PASS/FAIL
receipt to stdout and writes artifacts/seeded_demo_receipt.json. Exit 0 on PASS.
"""
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from src.fabric import discovery
from src.fabric.registry import Registry
from src.fabric.session import SessionJournal
from src.forge.manual_skill import compile_skill, render_command, replay
from src.mcp import server as mcp
from src.runtime.grounded import GroundedError, ChallengeStore, bind, verify_handle
from src.server import create_server

SALT = b'demo-salt-16bytes'
EVIDENCE = b'simulated-frame-sha-pixels'


class Loopback:
    def __init__(self): self.shown = {}
    def present(self, device_key, nonce): self.shown[device_key] = nonce
    def observe(self, device_key, timeout_s): return self.shown.get(device_key)


def fragment():
    return {'name': 'capture_waveform', 'version': '1.0.0', 'title': 'Oscilloscope manual excerpts',
            'parameters': [{'name': 'volts_per_div', 'unit': 'V', 'min': 0.1, 'max': 10.0, 'cite': 'manual.pdf:12'}],
            'warnings': [{'text': 'Never exceed 10 V on CH1.', 'cite': 'manual.pdf:14'}],
            'commands': [{'template': 'MEAS:CH1:RANGE {volts_per_div}V', 'cite': 'manual.pdf:12'}]}


def main():
    steps = []

    def step(name, func):
        t = time.monotonic()
        try:
            detail = func()
            steps.append({'name': name, 'ok': True, 'ms': round((time.monotonic() - t) * 1000, 1), 'detail': detail})
        except Exception as error:
            steps.append({'name': name, 'ok': False, 'ms': round((time.monotonic() - t) * 1000, 1), 'detail': f'{type(error).__name__}: {error}'})

    reg = Registry()
    obs = [{'address': 'C0:00:00:00:00:01', 'address_kind': 'static_random', 'rssi': -61, 'name': '', 'company_ids': [], 'service_uuids': []}]
    with mock.patch('src.fabric.discovery.now', return_value='2026-10-27T00:00:00+00:00'):
        discovery.ingest_ble(reg, {'devices': obs}, b'x', observer='pc', source='RELAY:r1')
    key = next(iter(reg.devices))
    server = create_server(0, fabric_salt=b'x', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
    server.fabric_registry, server.fabric_snapshot = reg, reg.snapshot()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    store = ChallengeStore()

    def do_bind():
        h = bind(store, SALT, key, Loopback(), evidence=EVIDENCE)
        body = verify_handle(SALT, h)
        assert body['device_key'] == key and body['evidence_sha256']
        return f"handle {h['handle_id']} bound to {key}"
    step('grounded-bind (loopback challenge)', do_bind)

    def do_adversarial():
        ch = store.issue(key)
        try:
            store.confirm(SALT, ch['challenge_id'], '00' * 16)
            raise AssertionError('wrong proof accepted')
        except GroundedError:
            pass
        h = bind(store, SALT, key, Loopback())
        try:
            verify_handle(SALT, dict(h, device_key='dev:other'))
            raise AssertionError('forged handle accepted')
        except GroundedError:
            pass
        return 'wrong proof refused, forged handle refused'
    step('adversarial minute (deterministic)', do_adversarial)

    box = {}

    def do_skill():
        skill = compile_skill(fragment())
        assert render_command(skill, {'volts_per_div': 2.0}) == 'MEAS:CH1:RANGE 2.0V'
        try:
            render_command(skill, {'volts_per_div': 12.0})
            raise AssertionError('over-range accepted')
        except Exception as error:
            assert 'manual.pdf:14' in str(error)
        rep = replay(skill, [{'params': {'volts_per_div': 1.0}, 'expected': 'MEAS:CH1:RANGE 1.0V'},
                              {'params': {'volts_per_div': 5.0}, 'expected': 'MEAS:CH1:RANGE 5.0V'}])
        assert (rep['passed'], rep['failed']) == (2, 0)
        box['hash'] = skill['fragment_hash'][:16]
        return f"skill {skill['name']} v{skill['version']} replay 2/2, hash {box['hash']}"
    step('manual2skill compile + replay', do_skill)

    def do_mcp():
        init = mcp.handle_message(base, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                         'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'demo', 'version': '0'}}})
        assert init['result']['serverInfo']['name'] == 'openbridge-mcp'
        tools = mcp.handle_message(base, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})['result']['tools']
        assert len(tools) == 3 and all(t['annotations']['readOnlyHint'] for t in tools)
        facts = mcp.handle_message(base, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                          'params': {'name': 'openbridge_get_facts', 'arguments': {'device': key}}})
        body = json.loads(facts['result']['content'][0]['text'])
        assert body['device'] == key and body['facts']
        evil = mcp.handle_message(base, {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                                         'params': {'name': 'openbridge_exec', 'arguments': {}}})
        assert evil['result']['isError'] is True
        return f"mcp {init['result']['protocolVersion']}: 3 read-only tools, facts ok, unknown tool refused"
    step('mcp read path + refusal', do_mcp)

    server.shutdown(); server.server_close()
    receipt = {'label': 'SIMULATED_DEMO', 'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'models_used': [],
               'note': 'Deterministic doubles only. No camera, no Companion channel, no model calls.',
               'steps': steps, 'verdict': 'PASS' if all(s['ok'] for s in steps) else 'FAIL'}
    Path('artifacts/seeded_demo_receipt.json').write_text(json.dumps(receipt, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=1))
    raise SystemExit(0 if receipt['verdict'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
