# Connect your own AI or API

OpenBridge ships **no paid model**. Out of the box, every AI feature runs on your own machine,
for free:

| Tier in Ask | Model | Where it runs | Cost |
|---|---|---|---|
| **Fast** | Meta Llama 3.2 3B (`llama3.2:3b-instruct-q4_K_M`) | this PC (Ollama) | free |
| **Smart** | Muse Glimmer 30B (`muse-glimmer:30b-q4_K_M`, open weights) | this PC (Ollama) | free |
| **Pro** | **the AI you connect by hand** (this page) | wherever you point it | billed by your provider, if any |
| **Auto** | Fast/Smart first, then your connected AI if allowed | n/a | n/a |

Devices stay fully usable without any model. A model only turns plain-language requests into
intents, which you still approve before anything runs.

> **Removed in this version.** The former hosted Meta "Muse Spark" tier, its promotional-credit
> ledger, cloud budget, cloud escalation, hosted speech-to-text and the `--spend` flag are gone.
> Historical evidence that mentions them (under `docs/evidence/`, `docs/archive/`, `docs/audits/`)
> records past runs and is kept unchanged.

## What you can connect

Any server that speaks one of two APIs:

| `kind` | API | Examples |
|---|---|---|
| `openai` | `POST {base_url}/chat/completions` (OpenAI-compatible) | LM Studio, llama.cpp `llama-server`, vLLM, LocalAI, Jan, OpenRouter, Together, Groq, Mistral, OpenAI |
| `ollama` | `POST {base_url}/api/chat` | Ollama on another PC of your LAN, or a different Ollama port |

## From the app

**Settings → Connected AI → Connect an AI / API.** Pick a preset (LM Studio, Ollama, llama.cpp,
OpenRouter) or fill the fields by hand, then **Connect** and **Test**. The provider becomes the
**Pro** option in Ask. You can change the active provider, stop using it, or remove it at any time.

## From the command line

```bash
# LM Studio on this PC (no key)
python -m src.cli ai add --name lmstudio --kind openai \
  --base-url http://127.0.0.1:1234/v1 --model qwen2.5-7b-instruct

# Ollama on another PC of your home network
python -m src.cli ai add --name nas --kind ollama \
  --base-url http://192.168.1.20:11434 --model llama3.1:8b

# llama.cpp server
python -m src.cli ai add --name llamacpp --kind openai \
  --base-url http://127.0.0.1:8080/v1 --model local

# A hosted API: the key is typed at a hidden prompt and stored in the OS secret store
python -m src.cli ai add --name openrouter --kind openai \
  --base-url https://openrouter.ai/api/v1 --model meta-llama/llama-3.3-70b-instruct --store-key
#   ...or keep it in an environment variable instead:
python -m src.cli ai add --name openrouter --kind openai \
  --base-url https://openrouter.ai/api/v1 --model meta-llama/llama-3.3-70b-instruct \
  --api-key-env OPENROUTER_API_KEY

python -m src.cli ai list                    # providers, active one, local/remote, key stored?
python -m src.cli ai use openrouter          # choose the active provider
python -m src.cli ai test lmstudio           # sends "Reply with exactly: OK"
python -m src.cli ai test openrouter --consent ALLOW-REMOTE   # remote providers need consent
python -m src.cli ai remove openrouter       # also deletes its stored key
```

Then `python -m src.cli capabilities generate ... --model CUSTOM` (or `AUTO`) and the Ask panel's
**Pro** option use it. `python -m src.cli doctor` and `models status` show it as
`connected AI (manual)`.

Options: `--timeout-s 5..300` (default 60), `--max-tokens 64..8192` (default 1024),
`--json-mode` (asks for `response_format: json_object`; only if your server supports it),
`--no-activate` (add without making it active).

## HTTP API (local server)

| Method | Path | Body |
|---|---|---|
| GET | `/api/v2/ai/providers` | → `{active, providers[], kinds, paid_models_built_in: false}` |
| POST | `/api/v2/ai/providers` | `{name, kind, base_url, model, api_key?, api_key_env?, timeout_s?, max_tokens?, json_mode?, activate?}` |
| POST | `/api/v2/ai/providers/test` | `{name, consent?}` (`consent: true` required for a remote provider) |
| POST | `/api/v2/ai/providers/activate` | `{name}` (or `null` to stop using any) |
| POST | `/api/v2/ai/providers/remove` | `{name}` |

POST routes need the session CSRF token (`X-CSRF-Token`, from `GET /api/session`), like every
other write route. `api_key` is written to the OS secret store and never returned.

## Safety rules (enforced in code)

- **Keys never in a file or on the command line.** The provider file refuses an `api_key` field.
  Keys live in the OS secret store (Windows DPAPI, name `ai-key-<provider>`) or in an environment
  variable named with `--api-key-env`. Error messages never echo a key or a request body.
- **https outside your network.** Plain `http://` is accepted only for loopback and private LAN
  addresses (127.0.0.0/8, ::1, 10/8, 172.16/12, 192.168/16, link-local, `*.local`, `*.lan`).
- **Not on this PC means consent.** Only a loopback provider counts as *local*. Anything else,
  including another PC of your LAN, is labelled *outside this PC*: Ask asks for explicit consent
  per request, the kill switch still applies, and `ai test` needs `--consent ALLOW-REMOTE`.
- **Fail-closed registry.** A model call is allowed only to a built-in local model or to the exact
  (model, endpoint) pair the owner connected. Anything else is refused before any byte is sent.
- **No surprises on the wire.** System proxies are ignored, redirects are refused (the key is never
  forwarded to another host), responses are bounded (512 KB), replies must be one JSON object for
  intent parsing; anything else becomes *escalation required*, never a guessed action.
- **Still approval-first.** A connected AI only proposes an intent. The preview, the consent and
  the read-back verification are the same as with the local models.

## Where the list is stored

`%LOCALAPPDATA%\OpenBridge\ai_providers.json` on Windows, `~/.local/share/OpenBridge/ai_providers.json`
elsewhere (override with `OPENBRIDGE_AI_PROVIDERS`). It holds names, URLs and model ids only.
Outside Windows there is no OS secret store integration yet: use `--api-key-env`.
