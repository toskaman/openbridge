"""Merge a LoRA adapter into its base model and import the result into the local Ollama, quantized.

Production talks to models through Ollama (OllamaIntentTransport), with prompt-prefix caching and quantized weights,
which is far faster than the Hugging Face eval path. This script makes a trained adapter usable there:

    python dev/ai_training/export_ollama.py --base E:/OpenBridgeAI/models/qwen2.5-1.5b-instruct \\
        --adapter E:/OpenBridgeAI/runs/qwen1.5b_v2/adapter --name openbridge-intent-qwen1.5b-v2 \\
        --out E:/OpenBridgeAI/export --quantize int4 int8

Ollama 0.40 imports safetensors with --quantize int4 | int8 | nvfp4 | mxfp4 | mxfp8 (the GGUF k-quants such as q4_K_M
are not offered for safetensors imports any more). --skip-merge reuses an existing <out>/<name>/hf.

It writes <out>/<name>/hf (merged safetensors), one Modelfile per quantization, and <out>/<name>/export.json with
the Ollama tag and digest of every created model (the digest is what config/runtime_models.json pins).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', required=True)
    ap.add_argument('--name', required=True, help='Ollama model name, e.g. openbridge-intent-qwen1.5b-v2')
    ap.add_argument('--out', required=True)
    ap.add_argument('--quantize', nargs='+', default=['int4'])
    ap.add_argument('--skip-merge', action='store_true')
    ap.add_argument('--endpoint', default='http://127.0.0.1:11434')
    a = ap.parse_args(argv)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    root = Path(a.out) / a.name
    hf = root / 'hf'
    hf.mkdir(parents=True, exist_ok=True)
    if not (a.skip_merge and (hf / 'config.json').exists()):
        tok = AutoTokenizer.from_pretrained(a.adapter)
        model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16)
        model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
        model.save_pretrained(hf, safe_serialization=True)
        tok.save_pretrained(hf)
        print(json.dumps({'merged': str(hf)}), flush=True)

    created = []
    for q in a.quantize:
        tag = '%s:%s' % (a.name, q.lower().replace('_', '-'))
        quant = [] if q == 'none' else ['--quantize', q]
        mf = root / ('Modelfile.%s' % q)
        mf.write_text('FROM %s\nPARAMETER temperature 0\nPARAMETER num_ctx 4096\n' % hf.as_posix(), encoding='utf-8')
        r = subprocess.run(['ollama', 'create', tag, *quant, '-f', str(mf)], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        print(r.stdout[-2000:], r.stderr[-2000:], flush=True)
        if r.returncode != 0:
            print(json.dumps({'error': 'ollama create failed', 'tag': tag}), flush=True)
            return 1
        created.append(tag)
    with urlopen(a.endpoint + '/api/tags', timeout=30) as resp:
        tags = {m['name']: m for m in json.loads(resp.read())['models']}
    meta = {'base': a.base, 'adapter': a.adapter, 'models': [
        {'tag': t, 'digest': tags.get(t, {}).get('digest'), 'size': tags.get(t, {}).get('size'),
         'quantization': tags.get(t, {}).get('details', {}).get('quantization_level')} for t in created]}
    (root / 'export.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    print(json.dumps(meta), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
