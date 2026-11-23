"""Score a model on the held-out OpenBridge command test set, through the same gate as production.

Backends:
  hf      a Hugging Face model, optionally with a LoRA adapter (--adapter)
  ollama  a model served by the local Ollama (same request shape as OllamaIntentTransport)

A request is "fully correct" when the router's decision class (resolved / needs_clarification / unsupported)
matches the gold one and, when resolved, the skill, the params and the target refs all match.
The router's own _interpret() is applied to every reply, so a malformed or invented reply is scored exactly
as production would treat it (escalation_required, never a guessed command).

    python dev/ai_training/evaluate.py --backend hf --model E:/OpenBridgeAI/models/qwen2.5-1.5b-instruct \
        --adapter E:/OpenBridgeAI/runs/qwen1.5b/adapter --data E:/OpenBridgeAI/data --out result.json

--split picks the file: test (held-out templates, default) or novel (the independent hand-written set).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.runtime import intent as I  # noqa: E402
from src.runtime import nl_router as NR  # noqa: E402

SYSTEM = 'Reply in English only as compact JSON matching the schema.'


def gold_class(reply):
    if reply['skill_id']:
        return 'resolved'
    return 'needs_clarification' if reply['clarifying_question'] else 'unsupported'


def score(row, raw):
    try:
        reply = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        reply = None
    doc = I.new_intent(row['text'], row['lang'])
    decided = NR._interpret(doc, reply, 'local', 'eval')
    g = row['reply']
    want = gold_class(g)
    ok = decided['status'] == want
    if ok and want == 'resolved':
        ok = (decided['skill_id'] == g['skill_id'] and decided['params'] == g['params']
              and sorted(t['ref'] for t in decided['targets']) == sorted(t['ref'] for t in g['targets']))
    return {'valid_json': isinstance(reply, dict), 'status': decided['status'], 'want': want,
            'skill': decided.get('skill_id'), 'want_skill': g['skill_id'], 'correct': ok}


class HF:
    def __init__(self, model, adapter=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(adapter or model)
        self.m = AutoModelForCausalLM.from_pretrained(model, dtype=torch.bfloat16, device_map={'': 0})
        if adapter:
            from peft import PeftModel
            self.m = PeftModel.from_pretrained(self.m, adapter)
        self.m.eval()

    def __call__(self, prompt):
        msgs = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]
        enc = self.tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors='pt', return_dict=True)
        ids = enc['input_ids'].to('cuda')
        with self.torch.no_grad():
            out = self.m.generate(ids, max_new_tokens=200, do_sample=False, pad_token_id=self.tok.eos_token_id)
        text = self.tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        start, end = text.find('{'), text.rfind('}')
        return text[start:end + 1] if start >= 0 and end > start else text


class Ollama:
    def __init__(self, model, endpoint='http://127.0.0.1:11434'):  # noqa: D107
        self.model, self.endpoint = model, endpoint

    def __call__(self, prompt):
        from urllib.request import Request, urlopen
        body = {'model': self.model, 'stream': False, 'format': NR.INTENT_SCHEMA, 'keep_alive': '10m',
                'options': {'temperature': 0, 'num_ctx': 4096},
                'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]}
        req = Request(self.endpoint + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=300) as r:
            return json.loads(r.read())['message']['content']


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=['hf', 'ollama'], required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--adapter', default=None)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--split', default='test', help='test | novel (file <split>.jsonl in --data)')
    ap.add_argument('--endpoint', default='http://127.0.0.1:11434', help='Ollama endpoint (ollama backend)')
    a = ap.parse_args(argv)
    rows = [json.loads(l) for l in open(Path(a.data) / ('%s.jsonl' % a.split), encoding='utf-8')]
    if a.limit:
        rows = rows[:a.limit]
    run = HF(a.model, a.adapter) if a.backend == 'hf' else Ollama(a.model, a.endpoint)
    results, lat = [], []
    for row in rows:
        t = time.perf_counter()
        try:
            raw = run(row['prompt'])
        except Exception as e:
            raw = 'ERROR %s' % type(e).__name__
        lat.append(time.perf_counter() - t)
        r = score(row, raw)
        r.update(family=row['family'], lang=row['lang'], text=row['text'], raw=str(raw)[:400])
        results.append(r)
    n = len(results)
    by_family = {}
    for r in results:
        f = by_family.setdefault(r['family'], [0, 0])
        f[0] += r['correct']
        f[1] += 1
    lat.sort()
    summary = {'model': a.model, 'adapter': a.adapter, 'backend': a.backend, 'split': a.split, 'n': n,
               'fully_correct_pct': round(100 * sum(r['correct'] for r in results) / n, 1),
               'valid_json_pct': round(100 * sum(r['valid_json'] for r in results) / n, 1),
               'decision_class_pct': round(100 * sum(r['status'] == r['want'] for r in results) / n, 1),
               'invented_or_wrong_action': sum(1 for r in results if r['status'] == 'resolved' and not r['correct']),
               'latency_p50_s': round(lat[n // 2], 2), 'latency_p95_s': round(lat[int(n * 0.95) - 1], 2),
               'by_family_pct': {k: round(100 * v[0] / v[1], 1) for k, v in sorted(by_family.items())},
               'by_lang_pct': {l: round(100 * sum(r['correct'] for r in results if r['lang'] == l) /
                                        max(1, sum(1 for r in results if r['lang'] == l)), 1) for l in ('en', 'fr')}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
