"""Merge a LoRA adapter into its base model and write one GGUF file for the phone (llama.cpp on the Companion).

    python dev/ai_training/export_gguf.py --base D:/OpenBridgeAI/hf/qwen3.5-0.8b \\
        --adapter D:/OpenBridgeAI/runs/phone_v1/adapter --out D:/OpenBridgeAI/export/phone_v1 \\
        --llama-cpp D:/OpenBridgeAI/llama.cpp --outtype q8_0

Writes <out>/hf (merged weights) and <out>/intent.gguf, the file `openbridge companion ai push` copies to the phone.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--llama-cpp', required=True, help='llama.cpp source folder (convert_hf_to_gguf.py)')
    ap.add_argument('--outtype', default='q8_0', choices=['q8_0', 'bf16', 'f16'])
    ap.add_argument('--skip-merge', action='store_true')
    a = ap.parse_args(argv)
    out = Path(a.out)
    hf = out / 'hf'
    if not a.skip_merge:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16)
        model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
        hf.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(hf, safe_serialization=True)
        AutoTokenizer.from_pretrained(a.adapter).save_pretrained(hf)
        print('merged ->', hf, flush=True)
    gguf = out / 'intent.gguf'
    r = subprocess.run([sys.executable, str(Path(a.llama_cpp) / 'convert_hf_to_gguf.py'), str(hf), '--outfile', str(gguf),
                        '--outtype', a.outtype], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        sys.exit('FAILED convert:\n' + r.stdout[-3000:] + r.stderr[-3000:])
    print('GGUF', gguf, gguf.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
