"""Accuracy of the phone command model on its held-out test set (exact JSON match), per family.

    python dev/ai_training/eval_phone.py --base D:/OpenBridgeAI/hf/qwen3.5-0.8b \\
        --adapter D:/OpenBridgeAI/runs/phone_v1/adapter --data D:/OpenBridgeAI/data_phone --out D:/OpenBridgeAI/runs/phone_v1/eval.json
"""
import argparse
import json
import time
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', default=None)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    system = (Path(a.data) / 'system.txt').read_text(encoding='utf-8')
    tok = AutoTokenizer.from_pretrained(a.adapter or a.base)
    model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16, device_map={'': 0})
    if a.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()
    rows = [json.loads(l) for l in open(Path(a.data) / 'test.jsonl', encoding='utf-8')]
    per, wrong, t0 = {}, [], time.time()
    for r in rows:
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': r['prompt']}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        if not prompt.rstrip().endswith('</think>'):
            prompt += '<think>\n\n</think>\n\n'
        ids = tok(prompt, return_tensors='pt', add_special_tokens=False).to('cuda')
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=40, do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()
        try:
            got = json.loads(text)
        except ValueError:
            got = None
        ok = got == r['reply']
        f = per.setdefault(r['family'], [0, 0])
        f[0] += ok
        f[1] += 1
        if not ok:
            wrong.append({'prompt': r['prompt'], 'want': r['reply'], 'got': text})
    total = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    doc = {'accuracy': round(total[0] / total[1], 4), 'n': total[1],
           'per_family': {k: round(v[0] / v[1], 3) for k, v in sorted(per.items())},
           'seconds': round(time.time() - t0), 'adapter': a.adapter, 'wrong': wrong}
    Path(a.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in doc.items() if k != 'wrong'}))
    for w in wrong[:15]:
        print('  x', w)


if __name__ == '__main__':
    main()
