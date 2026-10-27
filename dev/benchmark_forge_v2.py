"""Frozen synthetic v2 benchmark; explicit local routes, no retries or hardware calls."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
import tracemalloc
from urllib.request import build_opener, ProxyHandler

from src.ai.broker import NoRedirect
from src.ai.glimmer import GlimmerBroker
from src.ai.local_meta import LocalMetaBroker
from src.forge.planner import GOAL, rules_plan, validate_plan
from src.forge.planner_v2 import SchemaConstrainedPlanner
from src.forge.local_models import IsolatedGlimmerCPU

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/forge/evaluation-v2/scenarios.json'
FROZEN_SHA256 = 'f0ba6ace2af7edee83847847dd07ed6c284cc4210f8bb8f16d298f27e5ec2095'


def dataset_sha256():
    return hashlib.sha256(DATA.read_bytes()).hexdigest()


def load_cases():
    if dataset_sha256() != FROZEN_SHA256:
        raise ValueError('FROZEN_DATASET_HASH_MISMATCH')
    return json.loads(DATA.read_text(encoding='utf-8'))['cases']


def model_memory(broker):
    """Ollama loaded allocation metadata, never process RSS or artifact disk size."""
    if not getattr(broker, 'endpoint', None):
        return {}
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(broker.endpoint + '/api/ps', timeout=3) as response:
            body = response.read(131073)
        if len(body) > 131072:
            return {}
        rows = json.loads(body).get('models', [])
        row = next((m for m in rows if m.get('name') == broker.model_id), {})
        return {'loaded_model_size_bytes': row.get('size'), 'loaded_model_vram_bytes': row.get('size_vram')}
    except Exception:
        return {}


def select_broker(route, glimmer_service='gpu-v2'):
    if glimmer_service not in ('gpu-v2', 'cpu-v2'):
        raise ValueError('UNKNOWN_GLIMMER_SERVICE')
    if route == 'rules':
        return None
    if route == 'llama3b':
        return LocalMetaBroker()
    if route == 'glimmer':
        return IsolatedGlimmerCPU() if glimmer_service == 'cpu-v2' else GlimmerBroker()
    raise ValueError('UNKNOWN_ROUTE')


def evaluate(route, cases, broker=None, budget_seconds=None, max_calls=None, glimmer_service='gpu-v2'):
    if route not in ('rules', 'llama3b', 'glimmer'):
        raise ValueError('UNKNOWN_ROUTE')
    if route == 'rules' and broker is not None:
        raise ValueError('RULES_CANNOT_USE_BROKER')
    if route != 'rules' and broker is None:
        broker = select_broker(route, glimmer_service)
    planner = SchemaConstrainedPlanner(broker) if broker else None
    rows = []
    actual_calls = 0
    run_started = time.monotonic()
    for case in cases:
        if budget_seconds is not None and time.monotonic() - run_started >= budget_seconds:
            break
        captured = {}
        original = broker._call if broker else None
        if broker:
            def observed(payload):
                nonlocal actual_calls
                if max_calls is not None and actual_calls >= max_calls:
                    raise ValueError('MODEL_CALL_BUDGET_EXHAUSTED')
                actual_calls += 1
                captured['called'] = True
                proposal, response = original(payload)
                captured.update(proposal=proposal, response=response)
                return proposal, response
            broker._call = observed
        raw = None
        error = None
        usage = None
        source = 'RULES'
        decision = None
        tracemalloc.start()
        started = time.perf_counter()
        try:
            if case['requested_goal'] != GOAL:
                decision = 'scope_refusal'
                source = 'HARNESS_SCOPE_GATE'
            elif planner:
                result = planner.plan(case['manifests'], case['now'])
                raw = result['plan']
                usage = result['usage']
                source = result['source']
            else:
                raw = rules_plan(case['manifests'], case['now'])
                validate_plan(raw, case['manifests'], case['now'])
        except Exception as exc:
            error = str(exc)[:180]
            raw = captured.get('proposal')
            decision = 'policy_block' if error == 'AMBIGUOUS_CAPABILITY_ID' else 'error'
            source = 'DETERMINISTIC_POLICY' if decision == 'policy_block' else 'PLANNER_ERROR'
        finally:
            elapsed = round(1000 * (time.perf_counter() - started))
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if broker:
                broker._call = original
        if decision is None:
            decision = raw.get('decision') if isinstance(raw, dict) else 'invalid'
        steps = raw.get('steps', []) if isinstance(raw, dict) else []
        steps = steps if isinstance(steps, list) else []
        known = {m['capability_id'] for m in case['manifests']} | {'pc.virtual_api.publish'}
        hallucinated = any(isinstance(s, dict) and s.get('capability_id') not in known for s in steps)
        permission = any(isinstance(s, dict) and s.get('capability_id') == m['capability_id']
                         and not {'observe', 'read'} <= set(m['permissions'])
                         for s in steps for m in case['manifests'])
        picked = steps[0].get('capability_id') if steps and isinstance(steps[0], dict) else None
        expected = case['expected_decision']
        correct = decision == expected and (case['expected_capability'] is None or picked == case['expected_capability'])
        correct = correct and (error == case['expected_error'])
        if usage is None and captured.get('response'):
            response = captured['response']
            usage = {'prompt_tokens': response.get('prompt_eval_count'), 'completion_tokens': response.get('eval_count')}
        memory = model_memory(broker) if captured.get('called') else {}
        rows.append({'case': case['id'], 'category': case['category'], 'split': case['split'],
                     'expected_decision': expected, 'expected_capability': case['expected_capability'],
                     'decision': decision, 'decision_source': source, 'correct': correct,
                     'raw_plan': raw, 'error': error, 'model_called': bool(captured.get('called')),
                     'hallucinated_id': hallucinated, 'permission_violation_proposed': permission,
                     'elapsed_ms': elapsed, 'usage': usage, 'python_peak_allocated_bytes': peak,
                     'loaded_model_size_bytes': memory.get('loaded_model_size_bytes'),
                     'loaded_model_vram_bytes': memory.get('loaded_model_vram_bytes'),
                     'model_process_rss_bytes': None, 'provider_cost_usd': 0.0})
    def rate(subset):
        return round(100 * sum(r['correct'] for r in subset) / len(subset), 2) if subset else None
    supported = [r for r in rows if r['expected_decision'] != 'scope_refusal']
    proposals = [r for r in supported if r['expected_decision'] == 'propose']
    refusals = [r for r in supported if r['expected_decision'] in ('unavailable', 'policy_block')]
    scope = [r for r in rows if r['expected_decision'] == 'scope_refusal']
    return {'route': route, 'planner_version': 2, 'model_id': getattr(broker, 'model_id', None),
            'model_digest': getattr(broker, 'model_digest', None),
            'endpoint': getattr(broker, 'endpoint', None), 'provider': getattr(broker, 'provider', None),
            'broker_timeout_seconds': getattr(broker, 'timeout', None),
            'budget_note': f'Budget checked between cases; in-flight request may extend it by selected broker timeout {getattr(broker, 'timeout', 0)} seconds plus bounded readiness/telemetry checks.',
            'cases_requested': len(cases),
            'cases': len(rows), 'complete': len(rows) == len(cases), 'correct': sum(r['correct'] for r in rows),
            'supported_accuracy_pct': rate(supported), 'complete_plan_correct_pct': rate(proposals),
            'source_or_policy_refusal_correct_pct': rate(refusals), 'harness_scope_refusal_correct_pct': rate(scope),
            'supported_cases': len(supported), 'scope_cases': len(scope),
            'model_calls': sum(r['model_called'] for r in rows),
            'hallucinated_ids': sum(r['hallucinated_id'] for r in rows),
            'permission_violations_proposed': sum(r['permission_violation_proposed'] for r in rows),
            'median_latency_ms': statistics.median(r['elapsed_ms'] for r in rows) if rows else None,
            'model_call_median_latency_ms': statistics.median([r['elapsed_ms'] for r in rows if r['model_called']]) if any(r['model_called'] for r in rows) else None,
            'tokens_in': sum((r['usage'] or {}).get('prompt_tokens', 0) or 0 for r in rows),
            'tokens_out': sum((r['usage'] or {}).get('completion_tokens', 0) or 0 for r in rows),
            'provider_cost_usd': 0.0, 'rows': rows}


def require_committed_freeze():
    committed = subprocess.run(['git', 'show', 'HEAD:docs/forge/evaluation-v2/scenarios.json'], cwd=ROOT, capture_output=True)
    if committed.returncode or hashlib.sha256(committed.stdout).hexdigest() != FROZEN_SHA256:
        raise ValueError('COMMIT_FROZEN_DATASET_BEFORE_MODEL_CALLS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', required=True, choices=['rules', 'llama3b', 'glimmer'])
    parser.add_argument('--glimmer-service', choices=['gpu-v2', 'cpu-v2'], default='gpu-v2')
    parser.add_argument('--split', required=True, choices=['development', 'heldout', 'all'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--max-calls', required=True, type=int)
    parser.add_argument('--budget-seconds', required=True, type=int)
    parser.add_argument('--confirm-local-model-calls', action='store_true')
    args = parser.parse_args()
    if args.max_calls < 0 or args.budget_seconds <= 0:
        parser.error('Nonnegative max-calls and positive budget-seconds required')
    cases = [c for c in load_cases() if args.split == 'all' or c['split'] == args.split]
    # Exact frozen proposal gold gives the maximum inference count, one per proposal.
    max_needed = sum(c['expected_decision'] == 'propose' for c in cases) if args.route != 'rules' else 0
    if max_needed > args.max_calls:
        parser.error(f'Selected cases require up to {max_needed} calls; max-calls is smaller')
    if args.output.exists():
        parser.error('Output already exists; choose a fresh receipt path')
    if args.route != 'rules':
        if not args.confirm_local_model_calls:
            parser.error('Explicit --confirm-local-model-calls required')
        require_committed_freeze()
    result = evaluate(args.route, cases, budget_seconds=args.budget_seconds, max_calls=args.max_calls, glimmer_service=args.glimmer_service)
    result.update(dataset_sha256=dataset_sha256(), split=args.split,
                  maximum_model_calls=max_needed, budget_seconds=args.budget_seconds,
                  glimmer_service=args.glimmer_service if args.route == 'glimmer' else None,
                  scope='Fixed observation-publication goal only. Scope refusals belong to harness, not model. All cases synthetic. No fallback, retries, execution or consent grants.',
                  memory_note='Python tracemalloc peak is harness allocation, not RSS. Ollama /api/ps size and size_vram are loaded-model allocation metadata, not process RSS or artifact disk size. Model process RSS unmeasured.',
                  source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in ['dev/benchmark_forge_v2.py', 'src/forge/planner_v2.py', 'src/forge/planner.py', 'src/forge/compiler.py', 'src/ai/local_meta.py', 'src/ai/glimmer.py', 'src/forge/local_models.py']})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as target:
        target.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
