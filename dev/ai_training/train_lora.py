"""LoRA fine-tuning of a small local model on the OpenBridge command dataset.

The model sees exactly the production conversation (system line + build_prompt) and learns to answer with the
compact JSON the router expects. Loss is computed on the answer only. Everything is written under --out (E:).

    python dev/ai_training/train_lora.py --base E:/OpenBridgeAI/models/qwen2.5-1.5b-instruct \
        --data E:/OpenBridgeAI/data --out E:/OpenBridgeAI/runs/qwen1.5b
"""
import argparse
import json
import math
import random
import time
from pathlib import Path

SYSTEM = 'Reply in English only as compact JSON matching the schema.'


def answer(reply):
    return json.dumps(reply, ensure_ascii=False, separators=(', ', ': '))


def encode(tok, row, max_len):
    msgs = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': row['prompt']}]
    prefix = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    p_ids = tok(prefix, add_special_tokens=False)['input_ids']
    a_ids = tok(answer(row['reply']) + tok.eos_token, add_special_tokens=False)['input_ids']
    ids = (p_ids + a_ids)[:max_len]
    labels = ([-100] * len(p_ids) + a_ids)[:max_len]
    return ids, labels


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--epochs', type=float, default=2.0)
    ap.add_argument('--lr', type=float, default=2e-4)
    ap.add_argument('--rank', type=int, default=16)
    ap.add_argument('--accum', type=int, default=8)
    ap.add_argument('--max-len', type=int, default=2560)
    ap.add_argument('--init-adapter', default=None, help='continue training an existing LoRA adapter')
    ap.add_argument('--max-minutes', type=float, default=0, help='stop (and save) after this long')
    ap.add_argument('--limit', type=int, default=0, help='train on the first N examples only (smoke runs)')
    a = ap.parse_args(argv)

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(7)
    random.seed(7)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(a.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    rows = [json.loads(l) for l in open(Path(a.data) / 'train.jsonl', encoding='utf-8')]
    if a.limit:
        rows = rows[:a.limit]
    data = [encode(tok, r, a.max_len) for r in rows]
    model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16, device_map={'': 0})
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    if a.init_adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.init_adapter, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, task_type='CAUSAL_LM',
                                                 target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']))
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.0)
    total_steps = math.ceil(len(data) * a.epochs / a.accum)
    warm = max(1, total_steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * max(0.05, 0.5 * (1 + math.cos(math.pi * min(1.0, s / total_steps)))))
    model.train()
    log, step, seen, t0, running = [], 0, 0, time.time(), 0.0
    order = []
    while len(order) < len(data) * a.epochs:
        idx = list(range(len(data)))
        random.shuffle(idx)
        order += idx
    order = order[:int(len(data) * a.epochs)]
    for i, k in enumerate(order):
        ids, labels = data[k]
        x = torch.tensor([ids], device='cuda')
        y = torch.tensor([labels], device='cuda')
        loss = model(input_ids=x, labels=y).loss / a.accum
        loss.backward()
        running += loss.item()
        seen += 1
        if seen % a.accum == 0 or i == len(order) - 1:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 10 == 0 or step == total_steps:
                row = {'step': step, 'of': total_steps, 'loss': round(running / 10 if step % 10 == 0 else running, 4),
                       'lr': sched.get_last_lr()[0], 'elapsed_s': round(time.time() - t0)}
                print(json.dumps(row), flush=True)
                log.append(row)
                running = 0.0
            if a.max_minutes and time.time() - t0 > a.max_minutes * 60:
                print(json.dumps({'stopped_early_at_step': step, 'of': total_steps}), flush=True)
                break
    model.save_pretrained(out / 'adapter')
    tok.save_pretrained(out / 'adapter')
    meta = {'base': a.base, 'examples': len(data), 'epochs': a.epochs, 'lr': a.lr, 'rank': a.rank, 'accum': a.accum,
            'trainable_params': trainable, 'steps': step, 'train_seconds': round(time.time() - t0),
            'gpu': torch.cuda.get_device_name(0), 'peak_vram_gb': round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)}
    (out / 'train_meta.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    (out / 'train_log.json').write_text(json.dumps(log), encoding='utf-8')
    print(json.dumps(meta))


if __name__ == '__main__':
    main()
