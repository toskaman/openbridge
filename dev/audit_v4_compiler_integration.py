"""Pinned real-kernel/Forge compiler tests using disposable exact Git fixtures."""
import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KERNEL = '7e6196a097a082459e2c4d10f35d2260425e6397'
FORGE = 'bc488db5c4d768ffda963ccbf461f2ba12af8617'


def run():
    hashes = {}
    with tempfile.TemporaryDirectory(prefix='ob-review-') as directory:
        root = Path(directory)
        def materialize(path, ref):
            data = subprocess.check_output(['git', 'show', ref+':'+path])
            target = root/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[ref+':'+path] = hashlib.sha256(data).hexdigest()
            return target
        def load(name, path, ref):
            target = materialize(path, ref)
            spec = importlib.util.spec_from_file_location(name, target,
                submodule_search_locations=[str(target.parent)] if path.endswith('__init__.py') else None)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            parent, _, child = name.rpartition('.')
            if parent in sys.modules:
                setattr(sys.modules[parent], child, module)
            spec.loader.exec_module(module)
            return module
        import src.forge, tests
        for name in ['v4_schemas', 'v4_evidence', 'v4_metaclient', 'v4_synthesize', 'v4_substrate']:
            load('src.forge.'+name, 'src/forge/'+name+'.py', FORGE)
        materialize('src/substrate/v4_contract.schema.json', KERNEL)
        for name, path in [('src.substrate','src/substrate/__init__.py'),
                           ('src.substrate.registry','src/substrate/registry.py'),
                           ('src.substrate.kernel','src/substrate/kernel.py'),
                           ('tests.substrate','tests/substrate/__init__.py'),
                           ('tests.substrate.test_kernel','tests/substrate/test_kernel.py'),
                           ('tests.substrate.test_forge_wiring','tests/substrate/test_forge_wiring.py')]:
            load(name, path, KERNEL)
        battery = load('audit_pr82_tests', 'tests/forge/test_v4_layer.py', FORGE)
        suite = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromTestCase(sys.modules['tests.substrate.test_forge_wiring'].ForgeWiring),
            unittest.defaultTestLoader.loadTestsFromModule(battery)])
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
    return {'kernel_head': KERNEL, 'forge_head': FORGE, 'source_sha256': hashes,
            'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
            'skips': len(result.skipped), 'success': result.wasSuccessful(), 'test_output': output.getvalue(),
            'scope': 'Four real compiler/adapter tests plus34 agent-layer tests; fixture device observations and test key. No invoke/physical pipeline acceptance.',
            'actual_provider_calls': 0, 'actual_hardware_calls': 0, 'actual_spend_usd': 0,
            'release_gate': 'BLOCKED: accounting, provisioning, held-out and physical acceptance remain'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite receipts')
    report = run()
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(report['test_output'])
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
