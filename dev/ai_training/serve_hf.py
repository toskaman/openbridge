"""Serve a Hugging Face model (+ LoRA adapter) on a local Ollama-compatible /api/chat endpoint.

Used when Ollama cannot import the merged model (Ollama 0.40 on Windows needs the MLX runtime for safetensors):
evaluate.py --backend ollama --endpoint http://127.0.0.1:11500 and `openbridge ha say --endpoint ...` work unchanged.

    python dev/ai_training/serve_hf.py --base E:/OpenBridgeAI/models/llama-3.2-3b-instruct \
        --adapter E:/OpenBridgeAI/runs/llama3b_v3/adapter --port 11500
"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import HF  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', default=None)
    ap.add_argument('--port', type=int, default=11500)
    ap.add_argument('--name', default='openbridge-intent')
    a = ap.parse_args()
    model = HF(a.base, a.adapter)
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def do_POST(self):
            if self.path != '/api/chat':
                self.send_response(404)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            prompt = next((m['content'] for m in reversed(body.get('messages', [])) if m.get('role') == 'user'), '')
            with lock:
                text = model(prompt)
            out = json.dumps({'model': body.get('model', a.name), 'done': True, 'done_reason': 'stop',
                              'message': {'role': 'assistant', 'content': text}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    print('serving on 127.0.0.1:%d' % a.port, flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()


if __name__ == '__main__':
    main()
