"""Pinned owner-update probes; no provider, credentials or hardware."""
import argparse
import ast
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dev import audit_v4 as baseline

HEAD80 = '4f379e534b776914468144aa7f5eebf581c32a2b'
HEAD78 = 'eb2de8b39068876c3525b97dddc9f357679ea1e7'
HEAD81 = 'f4f2360'
HEAD72 = '366784fcbf039f18de26b3c7be60813eb70a76f6'


def raw(ref, path):
    return subprocess.check_output(['git', 'show', ref + ':' + path], text=True, encoding='utf-8')


def load(name, source):
    module = types.ModuleType(name)
    module.__package__ = name.rpartition('.')[0]
    sys.modules[name] = module
    exec(compile(source, name, 'exec'), module.__dict__)
    parent, _, child = name.rpartition('.')
    if parent in sys.modules:
        setattr(sys.modules[parent], child, module)
    return module


def run():
    import src.runtime
    original = src.runtime.command if hasattr(src.runtime, 'command') else None
    harness = inspect.getsource(baseline.probe_command_concurrency)
    if harness.count('barrier.wait(timeout=5)') != 1:
        raise RuntimeError('HARNESS_CHANGED')
    harness = harness.replace('barrier.wait(timeout=5)', 'time.sleep(0.1)')
    commands = {}
    for label, ref in [('before', 'dcf852775aab0a4129b1c9e117f9457db77f985d'), ('after', HEAD80)]:
        load('src.runtime.command', raw(ref, 'src/runtime/command.py'))
        scope = dict(vars(baseline)); scope['time'] = time
        exec(compile(harness, 'command_before_after_probe', 'exec'), scope)
        commands[label] = scope['probe_command_concurrency']()
    if original is not None:
        sys.modules['src.runtime.command'] = original
        src.runtime.command = original

    broker = load('audit_updated_broker', raw(HEAD78, 'src/ai/broker.py'))
    with tempfile.TemporaryDirectory() as directory:
        # Named fields protect against dataclass field-order changes.
        permit = broker.CreditPermit(observation_id='same-observation', verified_at=datetime.now(timezone.utc)-timedelta(seconds=600), free_balance_usd=139.8, session_budget_usd=.20)
        accepted = 0
        for output in ('out-a', 'out-b'):
            client = broker.RuntimeModelBroker(Path(directory)/output/'budget.sqlite3', permit,
                        evaluation_allowance_usd=.80, evaluation_authz='same-owner-authz')
            for _ in range(8):
                client._reserve()
                accepted += 1
    credit = {'head': HEAD78, 'reservations': accepted, 'reserved_usd': accepted*.1,
              'allowance_usd': .80, 'cross_output_cap_enforced': accepted <= 8}

    import src.forge
    load('src.forge.v4_schemas', raw(HEAD81, 'src/forge/v4_schemas.py'))
    wire = load('src.forge.v4_substrate', raw(HEAD81, 'src/forge/v4_substrate.py'))
    source = raw(HEAD72, 'src/substrate/kernel.py')
    selected = [n for n in ast.parse(source).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                and n.name in {'Substrate', 'canonical', 'manifest_hash'}]
    kernel = types.ModuleType('audit_actual_kernel72')
    kernel.time = time
    kernel.json = json
    kernel.hashlib = hashlib
    kernel.CONTRACT_VERSION = 'obv4.1'
    sys.modules[kernel.__name__] = kernel
    exec(compile(ast.Module(body=selected, type_ignores=[]), 'actual_kernel72', 'exec'), kernel.__dict__)
    instance = kernel.Substrate.__new__(kernel.Substrate)
    instance.compile = lambda manifest, facts: {'audit_mock_compile': True}
    manifest = {'label': 'héllo → tv'}
    wired = wire.compile_first(instance, manifest, [])
    adapter = {'wire_head': subprocess.check_output(['git', 'rev-parse', HEAD81], text=True).strip(),
               'kernel_head': HEAD72, 'result': wired,
               'hash_matches_actual_kernel': wired['manifest_hash'] == kernel.manifest_hash(manifest),
               'scope': 'Actual class/module helper resolution and Unicode hash; compile overridden, not end-to-end compilation.'}
    return {'commands': commands, 'credit': credit, 'adapter': adapter,
            'command_head': HEAD80, 'command_harness_sha256': hashlib.sha256(harness.encode()).hexdigest(),
            'actual_provider_calls': 0, 'actual_hardware_calls': 0, 'actual_spend_usd': 0,
            'release_gate': 'BLOCKED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite audit receipts')
    result = run()
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if (result['commands']['before']['mock_effects'] == 2
                 and result['commands']['after']['mock_effects'] == 1
                 and result['adapter']['hash_matches_actual_kernel']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

