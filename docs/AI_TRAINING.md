# OpenBridge's own command model

OpenBridge understands requests with a small local model trained for it: **Llama 3.2 3B + a LoRA adapter**,
running on the owner's own GPU. It never acts by itself: every reply goes through the router gate
(`src/runtime/nl_router.py`), a registered skill, the typed primitive, consent, and a read-back.

## The official model, everywhere a request is understood

Since 23 November 2026, `openbridge-intent:latest` is declared in [config/runtime_models.json](../config/runtime_models.json)
as the **official command model** (digest-pinned like the other built-in models, `src/ai/own_model.py`). It is tried
first by every path that turns words into a skill:

| Path | Before | Now |
|---|---|---|
| `openbridge ask`, the app's command box, `/api/v2/command` | Llama 3.2 3B (general) | **openbridge-intent**, then Llama 3.2 3B if absent |
| Voice and text from the Companions (phone, TV, watch) | Llama 3.2 3B | **openbridge-intent**, then Llama 3.2 3B |
| `openbridge ha say` | openbridge-intent | openbridge-intent |
| Planning, advice, generated UI (`propose`, `plan-text`, `compose-text`) | Llama 3.2 3B / Glimmer | unchanged: the command model only maps requests to skills |

Every answer says which model understood it (`understood_by` in `ask`, `provenance.model_id` in the intent). When the
command model is not installed, or answers something unusable, the general model takes over once; nothing is guessed.
`openbridge models list` shows whether it is installed and matches the pinned digest.

## What it understands (v3, 23 November 2026)

- **Three dialects:** French, US English and UK English ("pop the kettle on", "the big light", "lounge", "telly").
- **Every kind of home device:** about 30 kinds (lamps, LED strips, fairy lights, plugs, coffee machine, kettle,
  fans, heaters, AC, speakers, Sonos, soundbars, blinds, shutters, curtains, locks...) in 9 rooms. Device refs are
  canonical English ("la lampe de chevet" → `bedside lamp`), whatever the language of the request.
- **25 skills:** the original 12 plus `home.turn_on/turn_off/set_brightness/set_temperature/media_play/media_pause/
  media_volume/cover_open/cover_close/lock/undo`, `links.create` (new features by voice: "when the TV starts
  playing, dim the kitchen lights to 20 %"), `create.suggest` and `learn.report`.
- **Refusals and questions:** unlocking, garage doors, gates and alarms are refused; "turn it on" asks which device;
  "dim the lamp" asks for a value; things OpenBridge cannot do (pizza, weather, bins) are declined.

## How it was trained

| Step | Detail |
|---|---|
| Data | `dev/ai_training/make_dataset_v3.py`: 2 862 training lines (1 400 v2 commands + 1 462 home lines), typos, missing accents, fillers. 20 % of templates are test-only. |
| Independent test | `home_families.HOME_NOVEL` and `novel_test.py`: requests written by hand, never trained on. |
| Training | LoRA r16 continued from the v1 adapter, 1.2 epochs, lr 1.5e-4, 401 steps, 3 h 10 on an RTX 4060 Ti (9.4 GB VRAM). |
| Scoring | `evaluate.py`: every reply goes through the router's own `_interpret()`; "fully correct" = same decision, skill, params and device refs. |

## Results

Served by Ollama (GGUF q8_0, 3.4 GB), median **0.94 s** per request on an RTX 4060 Ti. The PyTorch adapter gives
exactly the same scores at 6.5 s.

| Test set | OpenBridge v3 (Llama 3.2 3B) | Llama 3.1 8B (general, 2.7× larger) |
|---|---|---|
| Home requests written by hand (36) | **100 %** | 16.7 % |
| Home held-out templates (141) | **90.8 %** (decision 95.7 %) | 23.4 % |
| All hand-written requests (202) | **96.0 %** (decision 98.5 %) | not run |
| Every held-out template, old and new skills (451) | **94.7 %** (decision 98.0 %; en 96.6 %, fr 92.6 %) | not run |

v1 (12 skills only) on its own test set: 96.6 %. Base Llama 3.2 3B before training: 39.7 %.

### Real test through OpenBridge on Home Assistant

`dev/ai_training/home_battery.py` runs 47 spoken requests through `openbridge ha say` against a real Home Assistant
(demo devices): model → router gate → typed primitive → Home Assistant → read-back.

| | Result |
|---|---|
| Understood (en-US / en-GB / fr) | **47 / 47** (100 % / 100 % / 100 %) |
| Acted and verified by read-back | **30 / 30**. First run 27 / 30: the 3 misses were thermostat requests sent to a heat/cool-range thermostat; fixed (only devices that support the action are matched) |
| Speed, request to read-back confirmed | median 1.1 s for understanding (Ollama) |
| Links created by voice | 3 / 3; one approved and fired for real: `VERIFIED` |
| Refusals | unlock, garage, alarm, pizza: all refused |

## Honest limits

- **French held-out phrasing is the weak spot:** 81.8 % vs 98.7 % in English on the held-out templates. Typical
  misses: rare slang ("boucle la porte"), "son de l'Echo à 32" read as play instead of volume, "sors les poubelles"
  read as emptying the vacuum's dustbin. On 17 hand-written chore requests ("sors les poubelles stp", "take the
  trash out please"), v3 is right only **47.1 %** of the time. Two fixes:
  - **A confirmation when the model hesitates** (in place now, every model): a robot-vacuum or TV skill whose request
    never names the device ("sors les poubelles" → empty the robot's bin) is asked back ("Vous parlez du robot
    aspirateur ?") instead of run. Typos are tolerated; on the training generator, fewer than 1 % of real vacuum and
    TV requests are asked back. Follow-ups ("pause it") keep their device from the conversation.
  - **v4 data** (`make_dataset_v4.py`): about 70 chore phrasings in French, US and UK English (bins, dishes, laundry,
    pets, plants...), all "no registered skill does this", next to every vacuum command that names the robot;
    hand-written chore requests held out (`chores_novel`). Retraining from the v3 adapter: see Results when done.
- **Ollama import:** Ollama 0.40 on Windows cannot import merged safetensors without the MLX runtime, so the model
  goes through a GGUF conversion with llama.cpp (`convert_hf_to_gguf.py --outtype q8_0`), then
  `ollama create openbridge-intent`. `dev/ai_training/serve_hf.py` serves the adapter directly when that is not
  possible (same scores, 6.5 s).
- **Demo devices only:** the real test used Home Assistant's demo integration, not physical bulbs or plugs yet.
- **`home.undo` across two separate `ha say` calls** has nothing to undo yet (the Undo snapshot lives in memory).

## Reproduce

```
python dev/ai_training/make_dataset_v3.py --out E:/OpenBridgeAI/data_v3
python dev/ai_training/train_lora.py --base <llama-3.2-3b-instruct> --data E:/OpenBridgeAI/data_v3 \
    --out E:/OpenBridgeAI/runs/llama3b_v3 --init-adapter E:/OpenBridgeAI/runs/llama3b/adapter --epochs 1.2 --lr 1.5e-4
python dev/ai_training/export_ollama.py --base <llama-3.2-3b-instruct> --adapter E:/OpenBridgeAI/runs/llama3b_v3/adapter \
    --name openbridge-intent --out E:/OpenBridgeAI/export   # merges; on Windows its Ollama import step fails (MLX)
python llama.cpp/convert_hf_to_gguf.py <merged dir> --outtype q8_0 --outfile openbridge-intent-v3-q8_0.gguf
ollama create openbridge-intent -f Modelfile      # FROM the .gguf + the Llama 3 chat template
python dev/ai_training/evaluate.py --backend ollama --model openbridge-intent --data E:/OpenBridgeAI/data_v3 \
    --split home_novel --out result.json
openbridge ha say "dim the kitchen lights to 30%" --consent ALLOW
```

## Partner adapters

A partner adapter adds one brand's product names and phrasings to this model, from a partner voice profile:
see [A voice model adapted to each partner](PARTNER_VOICE_MODEL.md).
