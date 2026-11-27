"""OpenBridge Voice AI Oracle — Real-time Q&A via phone microphone → glasses HUD.

Hybrid low-latency pipeline (FR + EN, web-grounded):
  1. MATH     -> Pure Python eval (< 1 ms)
  2. LOCATE   -> Curated offline KB (< 1 ms) or live DuckDuckGo + LLM
  3. GENERAL  -> Fast Cloud (Gemini Flash w/ Search Grounding, or Groq + ddgs)
                 OR Warm Local GPU (Ollama qwen2.5:7b-instruct + ddgs, keep_alive=-1)

The Oracle never executes device primitives. It is an *answer card*, not an intent.
It replies with <= 3 short lines (<= 32 chars/line) optimised for 304x256 MicroOLED.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import threading
import time
import urllib.request
from typing import Optional

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

# ---------------------------------------------------------------------------
# Fast local math evaluator — no model needed, < 1 ms
# ---------------------------------------------------------------------------
_SAFE_MATH = re.compile(r'^[\d\s\+\-\*\/\%\(\)\.e]+$')
_MATH_TRIGGERS = re.compile(
    r'\b(?:combien|calcul\w*|fois|divis\w*|multipl\w*|plus|moins|racine|carre|puissance|'
    r'sqrt|pow|percent|pourcent|how\s+much|what\s+is\s+[\d]|[\d]+\s*[\+\-\*\/x×÷]\s*[\d])\b',
    re.IGNORECASE,
)
_LOCATE_TRIGGERS = re.compile(
    r'\b(?:où\s+(?:est|se\s+trouve|est\s+situé)|ou\s+(?:est|se\s+trouve)|'
    r'capitale|population|superficie|meteo|météo|quel\s+temps|'
    r'where\s+is|what\s+is\s+the\s+capital|weather|forecast|'
    r'distance\s+(?:de|entre|from)|combien\s+de\s+km|'
    r'qui\s+est|who\s+is|quand|when\s+is|prix|price|cours\s+du)\b',
    re.IGNORECASE,
)


def _normalise_expr(text: str) -> str:
    """Convert spoken math to Python expr: '2 fois 6' -> '2*6', '12 sur 4' -> '12/4'."""
    t = text.lower()
    t = re.sub(
        r'\b(?:combien\s+(?:fait|vaut|donne|font)\s*|'
        r'(?:calcule|calculate|compute|what\s+is|how\s+much\s+is)\s*)',
        '', t
    )
    t = re.sub(r'\b(fois|multiplié\s+par|multiplie\s+par|multiplié|times|x)\b', '*', t)
    t = re.sub(r'\b(divisé\s+par|divise\s+par|divisé|divided\s+by|sur)\b', '/', t)
    t = re.sub(r'\b(plus)\b', '+', t)
    t = re.sub(r'\b(moins)\b', '-', t)
    t = re.sub(r'\bracine\s+(?:carré\s+|carree\s+)?de\b', 'sqrt', t)
    t = re.sub(r'\bau\s+carré\b|\bau\s+carre\b', '**2', t)
    t = re.sub(r'\bpuissance\b', '**', t)
    t = re.sub(r'[^\d\+\-\*\/\%\(\)\.e_sqrt\*]', '', t)
    return t


def _try_math(text: str) -> Optional[str]:
    """Return formatted math result or None."""
    expr = _normalise_expr(text)
    if 'sqrt' in expr:
        expr = re.sub(r'sqrt(\d+(?:\.\d+)?)', r'math.sqrt(\1)', expr)
        try:
            result = eval(expr, {"__builtins__": {}, "math": math})  # noqa: S307
        except Exception:
            return None
    elif _SAFE_MATH.match(expr) and expr:
        try:
            result = eval(expr, {"__builtins__": {}})  # noqa: S307
        except Exception:
            return None
    else:
        return None
    if isinstance(result, float) and result == int(result):
        result = int(result)
    elif isinstance(result, float):
        result = round(result, 4)
    return str(result)


# Triggers requiring live internet lookup (weather, news, prices, sports, schedules)
_NEEDS_WEB_RX = re.compile(
    r'\b(?:meteo|météo|quel\s+temps|pluie|temperature|température|weather|forecast|'
    r'actualit\w*|news|aujourd\'?hui|today|hier|yesterday|demain|tomorrow|ce\s+soir|tonight|'
    r'prix|price|cours\s+du|bourse|bitcoin|btc|eth|euro|dollar|action\s+|stock|'
    r'score|match|gagn[ée]|classement|resultat|résultat|qui\s+a\s+gagn|'
    r'horaire\w*|ouvert|ferme|fermé|trafic|traffic|rer|metro|métro|train|vol\s+|flight|'
    r'en\s+ce\s+moment|maintenant|right\s+now|currently|live|latest|dernier\w*)\b',
    re.IGNORECASE,
)


def needs_web(transcript: str) -> bool:
    """Return True only when the query requires live/fresh internet data."""
    if os.environ.get('OB_ORACLE_FORCE_WEB') == '1':
        return True
    return bool(_NEEDS_WEB_RX.search(transcript))


# ---------------------------------------------------------------------------
# Query class detection
# ---------------------------------------------------------------------------
def classify(transcript: str) -> str:
    """'MATH' | 'LOCATE' | 'GENERAL'"""
    if _MATH_TRIGGERS.search(transcript):
        return 'MATH'
    if _LOCATE_TRIGGERS.search(transcript):
        return 'LOCATE'
    return 'GENERAL'


# ---------------------------------------------------------------------------
# Fast Web Search (DuckDuckGo lite + 120s cache + speculative pre-fetch)
# ---------------------------------------------------------------------------
_WEB_LOCK = threading.Lock()
_WEB_CACHE: dict[str, tuple[float, str]] = {}
_WEB_INFLIGHT: set[str] = set()
_WEB_TTL_S = 120.0
_WEB_MAX = 128


def _web_search(query: str, max_results: int = 2, timeout: float = 1.3) -> str:
    """Return compact web snippets (cached 120s) or '' on failure/timeout."""
    if os.environ.get('OB_ORACLE_WEB', '1') == '0':
        return ''
    norm_q = ' '.join(query.lower().split())
    if not norm_q:
        return ''
    now = time.monotonic()
    with _WEB_LOCK:
        hit = _WEB_CACHE.get(norm_q)
        if hit and (now - hit[0]) < _WEB_TTL_S:
            return hit[1]
    try:
        from ddgs import DDGS
        results = None
        for backend in ('lite', 'auto'):
            try:
                results = DDGS(timeout=timeout).text(query, max_results=max_results, backend=backend)
                if results:
                    break
            except Exception:
                continue
        snippets = []
        for r in results or []:
            title = (r.get('title') or '').strip()
            body = (r.get('body') or '').strip()
            if body:
                snippets.append(f"- {title}: {body[:140]}")
        out = '\n'.join(snippets)
        if out:
            with _WEB_LOCK:
                if len(_WEB_CACHE) >= _WEB_MAX:
                    _WEB_CACHE.pop(next(iter(_WEB_CACHE)))
                _WEB_CACHE[norm_q] = (time.monotonic(), out)
        return out
    except Exception:
        return ''


def prefetch_web(transcript: str) -> bool:
    """Speculatively warm _WEB_CACHE from a partial transcript when needs_web() holds."""
    if os.environ.get('OB_ORACLE_WEB', '1') == '0' or not needs_web(transcript):
        return False
    norm_q = ' '.join(transcript.lower().split())
    if len(norm_q) < 6:
        return False
    with _WEB_LOCK:
        hit = _WEB_CACHE.get(norm_q)
        if hit and (time.monotonic() - hit[0]) < _WEB_TTL_S:
            return True
        if norm_q in _WEB_INFLIGHT:
            return False
        _WEB_INFLIGHT.add(norm_q)

    def _run():
        try:
            _web_search(transcript, max_results=2, timeout=1.3)
        finally:
            with _WEB_LOCK:
                _WEB_INFLIGHT.discard(norm_q)

    threading.Thread(target=_run, name='oracle-web-prefetch', daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# LLM Backends (Cloud Fast -> Local Warm GPU via 127.0.0.1 keep-alive)
# ---------------------------------------------------------------------------
_OLLAMA_URL = os.environ.get('OB_OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
# qwen2.5:7b-instruct is bilingual FR/EN and fits comfortably in 16GB VRAM
_OLLAMA_MODEL = os.environ.get('OB_ORACLE_MODEL', 'qwen2.5:7b-instruct')
_LLAMA_CPP_URL = os.environ.get('OB_LLAMACPP_URL', 'http://127.0.0.1:8080/completion')
_GROQ_MODEL = os.environ.get('OB_GROQ_MODEL', 'llama-3.1-8b-instant')
_GEMINI_MODEL = os.environ.get('OB_GEMINI_MODEL', 'gemini-2.5-flash')
# R12: no built-in third-party endpoint. The owner opts in by setting
# OB_GEMINI_URL_BASE (e.g. their Gemini-compatible base URL); otherwise
# the cloud backend stays disabled and local backends are used.
_GEMINI_URL_BASE = os.environ.get('OB_GEMINI_URL_BASE', '')

_HTTP_LOCK = threading.Lock()
_HTTP_CLIENT = None


def _http_post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: float = 5.0) -> Optional[dict]:
    """POST JSON reusing a persistent HTTP/1.1 keep-alive connection when httpx is available."""
    global _HTTP_CLIENT
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if _httpx is not None:
        with _HTTP_LOCK:
            if _HTTP_CLIENT is None:
                _HTTP_CLIENT = _httpx.Client(
                    limits=_httpx.Limits(max_keepalive_connections=8, max_connections=16),
                )
        resp = _HTTP_CLIENT.post(url, json=payload, headers=hdrs, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

ORACLE_SYSTEM_PROMPT = (
    "You are an ultra-fast assistant inside ENGO 3 smart glasses (304x256 HUD). "
    "Reply in the EXACT same language as the user (French or English). "
    "STRICT FORMAT: maximum 3 short lines, maximum 32 characters per line. "
    "NO markdown, NO asterisks, NO greetings. Just the direct factual answer."
)


def _call_gemini_grounded(prompt: str, timeout: float = 3.5) -> Optional[str]:
    """Call the owner-provided Gemini-compatible endpoint with Search Grounding.

    Needs GEMINI_API_KEY (or GOOGLE_API_KEY) plus OB_GEMINI_URL_BASE.
    Returns None when the owner did not opt into a cloud backend.
    """
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key or not _GEMINI_URL_BASE:
        return None
    try:
        url = (
            f"{_GEMINI_URL_BASE.rstrip('/')}/models/"
            f"{_GEMINI_MODEL}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": ORACLE_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": 64, "temperature": 0.1},
        }
        data = _http_post_json(url, payload, timeout=timeout)
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        return None


def _call_groq(prompt: str, web_ctx: str = '', timeout: float = 2.5) -> Optional[str]:
    """Call Groq OpenAI-compatible endpoint (~300+ tok/s, free tier)."""
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return None
    try:
        user_msg = f"Web context:\n{web_ctx}\n\nQuestion: {prompt}" if web_ctx else prompt
        payload = {
            "model": _GROQ_MODEL,
            "messages": [
                {"role": "system", "content": ORACLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 64,
            "temperature": 0.1,
        }
        data = _http_post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _call_ollama(prompt: str, web_ctx: str = '', timeout: float = 8.0) -> Optional[str]:
    """Call local Ollama server with keep_alive=-1 so model stays hot in VRAM."""
    try:
        full_prompt = f"Infos web:\n{web_ctx}\n\nQuestion: {prompt}" if web_ctx else prompt
        payload = {
            "model": _OLLAMA_MODEL,
            "prompt": full_prompt,
            "system": ORACLE_SYSTEM_PROMPT,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "num_predict": 48,
                "num_ctx": 1024,
                "temperature": 0.1,
                "top_k": 10,
            }
        }
        data = _http_post_json(_OLLAMA_URL, payload, timeout=timeout)
        return data.get("response", "").strip()
    except Exception:
        return None


def _call_llamacpp(prompt: str, web_ctx: str = '', timeout: float = 4.0) -> Optional[str]:
    """Call llama.cpp server (/completion). Returns answer or None."""
    try:
        full_prompt = f"Infos web:\n{web_ctx}\n\nQuestion: {prompt}" if web_ctx else prompt
        payload = {
            "prompt": f"<|system|>\n{ORACLE_SYSTEM_PROMPT}\n<|user|>\n{full_prompt}\n<|assistant|>\n",
            "n_predict": 48,
            "temperature": 0.1,
            "top_k": 10,
            "stop": ["<|user|>", "<|system|>"],
        }
        data = _http_post_json(_LLAMA_CPP_URL, payload, timeout=timeout)
        return data.get("content", "").strip()
    except Exception:
        return None


def warmup() -> bool:
    """Preload local Ollama model into VRAM so first voice query has zero cold start."""
    global _WARMED
    try:
        _http_post_json(
            _OLLAMA_URL,
            {"model": _OLLAMA_MODEL, "prompt": "", "keep_alive": -1, "options": {"num_ctx": 1024}},
            timeout=20.0,
        )
        _WARMED = True
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Locate fast path: curated offline answers (< 1 ms)
# ---------------------------------------------------------------------------
_OFFLINE_KB: dict[str, str] = {
    "lac d'annecy": "Lac d'Annecy\nHaute-Savoie, France\n14,6 km2 - alt. 447m",
    "annecy": "Annecy\nHaute-Savoie, France\n~ 136 000 hab.",
    "capitale france": "Paris\nCapitale de la France\n2,1M hab. intra-muros",
    "capitale allemagne": "Berlin\nCapitale de l'Allemagne",
    "capitale espagne": "Madrid\nCapitale de l'Espagne",
    "capitale italie": "Rome\nCapitale de l'Italie",
}


def _offline_lookup(transcript: str) -> Optional[str]:
    if os.environ.get('OB_ORACLE_FORCE_WEB') == '1':
        return None
    t = transcript.lower()
    for key, answer in _OFFLINE_KB.items():
        if key in t:
            return answer
    return None


# ---------------------------------------------------------------------------
# HUD formatter (strip markdown, wrap <= 3 lines x 32 chars)
# ---------------------------------------------------------------------------
def _format_hud(text: str) -> str:
    clean = re.sub(r'[*_`#]+', '', text).strip()
    out_lines: list[str] = []
    for raw_line in clean.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        while len(raw_line) > 32 and len(out_lines) < 3:
            cut = raw_line.rfind(' ', 0, 32)
            if cut <= 0:
                cut = 32
            out_lines.append(raw_line[:cut].rstrip())
            raw_line = raw_line[cut:].lstrip()
        if raw_line and len(out_lines) < 3:
            out_lines.append(raw_line[:32])
        if len(out_lines) >= 3:
            break
    return '\n'.join(out_lines[:3])


# ---------------------------------------------------------------------------
# Fast in-memory TTL cache (60s) + recent history + HUD push helper
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_ANSWER_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_S = 60.0
_CACHE_MAX = 128
_RECENT_ANSWERS: list[dict] = []
_RECENT_MAX = 20
_WARMED = False


def recent_answers() -> list[dict]:
    """Return the latest 20 Oracle answers (newest last)."""
    with _CACHE_LOCK:
        return list(_RECENT_ANSWERS)


def status() -> dict:
    """Health/readiness summary for /api/v2/voice/oracle/status."""
    with _CACHE_LOCK:
        cache_len = len(_ANSWER_CACHE)
        recent = list(_RECENT_ANSWERS[-5:])
    return {
        "model": _OLLAMA_MODEL,
        "warmed": _WARMED,
        "cache_entries": cache_len,
        "cloud_gemini": bool((os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')) and _GEMINI_URL_BASE),
        "cloud_groq": bool(os.environ.get('GROQ_API_KEY')),
        "recent": recent,
    }


def _record_recent(res: dict, mic_source: Optional[str] = None) -> None:
    entry = dict(res)
    if mic_source:
        entry["mic_source"] = mic_source
    entry["at"] = time.time()
    with _CACHE_LOCK:
        _RECENT_ANSWERS.append(entry)
        del _RECENT_ANSWERS[:-_RECENT_MAX]


def push_oracle_to_hud(
    server,
    answer_data: dict,
    mic_source: Optional[str] = None,
    partial: bool = False,
) -> bool:
    """Push an Oracle result (or partial listening preview) to connected ENGO / HUD glasses."""
    pushed = False
    if server is not None:
        # 1. Native Glasses Hub (src.glasses.hub.Hub -> BleLink / StudioLink / NullLink)
        hub = getattr(server, 'glasses_hub', None)
        if hub is not None and hasattr(hub, 'oracle'):
            try:
                hub.oracle(str(answer_data.get('transcript', '')), answer_data, partial=partial)
                pushed = True
            except Exception:
                pass

        # 2. EngoAIBridge / ActiveLookAdapter
        glasses = getattr(server, 'engo_bridge', None) or getattr(server, 'activelook', None)
        if glasses is not None:
            adapter = getattr(glasses, 'adapter', glasses)
            try:
                if partial:
                    fn = getattr(adapter, 'push_neural_voice_assistant_hud', None)
                    if fn and fn(
                        state_str="ECOUTE ORACLE",
                        partial_transcript=str(answer_data.get('transcript', ''))[:48],
                        mic_source=(mic_source or "PHONE MIC").upper()[:24],
                        vu_level_pct=75,
                        latency_ms=0,
                        is_speaking=True,
                    ):
                        pushed = True
                else:
                    push_fn = getattr(glasses, 'push_oracle_answer', None) or getattr(adapter, 'push_oracle_answer', None)
                    if push_fn and push_fn(
                        query_class=answer_data.get('query_class', 'GENERAL'),
                        transcript=answer_data.get('transcript', ''),
                        answer=answer_data.get('answer', ''),
                        source=answer_data.get('source', 'unavailable'),
                        latency_ms=int(answer_data.get('latency_ms', 0)),
                    ):
                        pushed = True
            except Exception:
                pass

    # 3. Optional out-of-process `openbridge glasses run` Control IPC (opt-in via port attr or OB_GLASSES_IPC=1)
    ipc_port = getattr(server, 'glasses_control_port', None) if server is not None else None
    if not pushed and (ipc_port or os.environ.get('OB_GLASSES_IPC') == '1'):
        try:
            from src.glasses.cli import CONTROL_PORT, send
            port = int(ipc_port or os.environ.get('OB_GLASSES_PORT') or CONTROL_PORT)
            send({'oracle': answer_data, 'partial': partial}, port=port, timeout=0.4)
            pushed = True
        except Exception:
            pass

    if not partial and answer_data.get('answer'):
        _record_recent(answer_data, mic_source=mic_source)
    return pushed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
_VISION_MODEL = os.environ.get('OB_VISION_MODEL', '')
_VISION_PICK: dict = {}


def vision_model(timeout: float = 4.0) -> Optional[str]:
    """The local Ollama model used for the visual Oracle: OB_VISION_MODEL, or the smallest installed model that
    declares the 'vision' capability. None when there is none (the answer then says so)."""
    if _VISION_MODEL:
        return _VISION_MODEL
    if 'name' in _VISION_PICK and time.monotonic() - _VISION_PICK['at'] < 600:
        return _VISION_PICK['name']
    base = _OLLAMA_URL.rsplit('/api/', 1)[0]
    best = None
    try:
        with urllib.request.urlopen(base + '/api/tags', timeout=timeout) as r:
            models = json.loads(r.read()).get('models', [])
        for m in sorted(models, key=lambda m: m.get('size', 1 << 60)):
            info = _http_post_json(base + '/api/show', {'model': m['name']}, timeout=timeout) or {}
            if 'vision' in (info.get('capabilities') or []):
                best = m['name']
                break
    except Exception:
        best = None
    _VISION_PICK.update(name=best, at=time.monotonic())
    return best


def vision_answer(jpeg: bytes, question: str, lang: str = 'fr', timeout: float = 90.0) -> dict:
    """Visual Oracle: a photo from the phone and the owner's question, answered by a local vision model.
    Same result shape as oracle_answer (query_class VISION)."""
    t0 = time.monotonic()
    q = ' '.join(str(question or '').split()) or ("Qu'est-ce que c'est ?" if lang == 'fr' else 'What is this?')
    model = vision_model()
    answer, source = None, 'unavailable'
    if model:
        try:
            data = _http_post_json(_OLLAMA_URL, {
                'model': model, 'prompt': q, 'system': ORACLE_SYSTEM_PROMPT, 'stream': False, 'think': False,
                'images': [base64.b64encode(jpeg).decode('ascii')], 'keep_alive': '5m',
                'options': {'num_predict': 80, 'num_ctx': 4096, 'temperature': 0.2}}, timeout=timeout) or {}
            answer = (data.get('response') or '').strip() or None
            source = 'ollama_vision:' + model if answer else 'unavailable'
        except Exception:
            answer = None
    if not answer:
        answer = ("Pas de modele de vision\nsur ce PC" if lang == 'fr' else "No vision model\non this PC") if not model \
            else ("Image non analysee" if lang == 'fr' else "Could not read the image")
    return {'query_class': 'VISION', 'answer': _format_hud(answer), 'latency_ms': int((time.monotonic() - t0) * 1000),
            'source': source, 'transcript': q}


def oracle_answer(
    transcript: str,
    timeout: float = 8.0,
) -> dict:
    """
    Given a voice transcript, return:
    {
      "query_class": "MATH" | "LOCATE" | "GENERAL",
      "answer": "...",       # <= 3 short lines x 32 chars for HUD
      "latency_ms": int,
      "source": str,
      "transcript": str,
    }
    """
    t0 = time.monotonic()
    norm_key = ' '.join(transcript.lower().split())
    if norm_key:
        with _CACHE_LOCK:
            hit = _ANSWER_CACHE.get(norm_key)
            if hit and (t0 - hit[0]) < _CACHE_TTL_S:
                cached = dict(hit[1])
                cached["latency_ms"] = int((time.monotonic() - t0) * 1000)
                cached["transcript"] = transcript
                cached["cached"] = True
                return cached

    qclass = classify(transcript)
    answer: Optional[str] = None
    source = "unavailable"

    if qclass == 'MATH':
        answer = _try_math(transcript)
        if answer:
            source = "math_eval"
            answer = f"= {answer}"

    if answer is None and qclass == 'LOCATE' and not needs_web(transcript):
        answer = _offline_lookup(transcript)
        if answer:
            source = "offline_kb"

    if answer is None:
        # 1. Gemini Flash w/ native Google Search Grounding (fastest single-hop web)
        answer = _call_gemini_grounded(transcript, timeout=min(timeout, 3.5))
        if answer:
            source = "gemini_search"

    if answer is None:
        # 2. Fetch compact web snippets ONLY for live/news/weather/price queries
        web_ctx = _web_search(transcript, max_results=2, timeout=1.3) if needs_web(transcript) else ''

        # 3. Groq Cloud (ultra-fast free tier)
        answer = _call_groq(transcript, web_ctx=web_ctx, timeout=min(timeout, 2.5))
        if answer:
            source = "groq+web" if web_ctx else "groq"
        else:
            # 4. Warm local Ollama (qwen2.5:7b-instruct on RTX 4060 Ti via 127.0.0.1 keep-alive)
            answer = _call_ollama(transcript, web_ctx=web_ctx, timeout=timeout)
            if answer:
                source = "ollama+web" if web_ctx else "ollama"
            else:
                # 5. llama.cpp fallback
                answer = _call_llamacpp(transcript, web_ctx=web_ctx, timeout=min(timeout, 4.0))
                if answer:
                    source = "llamacpp+web" if web_ctx else "llamacpp"

    if not answer:
        answer = "Reponse indisponible\n(modele LLM absent)"
        source = "unavailable"

    res = {
        "query_class": qclass,
        "answer": _format_hud(answer),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "source": source,
        "transcript": transcript,
    }
    if norm_key and source != "unavailable":
        with _CACHE_LOCK:
            if len(_ANSWER_CACHE) >= _CACHE_MAX:
                _ANSWER_CACHE.pop(next(iter(_ANSWER_CACHE)))
            _ANSWER_CACHE[norm_key] = (time.monotonic(), dict(res))
    return res
