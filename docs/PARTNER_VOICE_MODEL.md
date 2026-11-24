# A voice model adapted to each partner

People say product names that no general model knows ("lance l'Acme X5", "switch the Glow lamp on"), and
speech-to-text mishears them ("acmé x cinq"). A **partner voice profile** teaches OpenBridge a partner's vocabulary
and phrasings, in the partner's languages, and everything stays offline: no audio and no text leave the home.

## What a profile changes

| Layer | Without a profile | With a profile |
|---|---|---|
| Speech-to-text (local MMS model) | "lance acmé x cinq" | same transcript, kept as heard for display and audit |
| Transcript repair (`voice_normalize`) | no match | "lance acme x5", the repair is listed (`acmé x cinq -> acme x5 (acme)`) |
| Intent model (`openbridge-intent`, Llama 3.2 3B + LoRA) | general home model | optional partner adapter trained on the partner's names and phrasings |
| Safety | | unchanged: a request that matches only thanks to a repair is asked back ("did you mean the Acme X5?"), never run directly |

## The profile

A JSON file, format `openbridge-voiceprofile/1`. A complete example (fictional brand) is in
[partners/examples/voice-profile.acme.json](partners/examples/voice-profile.acme.json).

- `products`: each with a canonical `ref`, a `kind` (light, appliance, thermostat, speaker, cover, lock, vacuum),
  the `names` people use per dialect (`fr`, `en-US`, `en-GB`, or any other language code) and the `misheard`
  variants measured on real recordings.
- `phrases`: the partner's own ways of asking (`"Envoie {d} en mission"` for starting a cleaning), attached to an
  existing request family. They add phrasings, never new actions: what a device can do is still decided by its
  typed skills and the policy.
- `languages`: the dialects the partner needs.

Checks on loading: a misheard variant can be neither an everyday word nor part of the product name itself, so a
profile can never rewrite ordinary speech.

## Languages

| Language | Speech-to-text | Intent model | What a new language needs |
|---|---|---|---|
| French | ready | ready | nothing |
| English (US, UK) | ready | ready | nothing |
| Other (de, es, it, nl…) | the local model has an adapter per language, not yet enabled or measured | not trained | enable the adapter, record and measure commands, write templates, train the partner adapter |

`partner_voice.coverage(profile)` prints this table for a given profile.

## Training a partner adapter

```
python dev/ai_training/make_partner_dataset.py --profile docs/partners/examples/voice-profile.acme.json \
    --base-data E:/OpenBridgeAI/data_v4 --replay 800 --out E:/OpenBridgeAI/data_partner_acme
python dev/ai_training/train_lora.py --base <llama-3.2-3b-instruct> --init-adapter E:/OpenBridgeAI/runs/llama3b_v4c/adapter \
    --data E:/OpenBridgeAI/data_partner_acme --out E:/OpenBridgeAI/runs/llama3b_partner_acme --epochs 1 --lr 1e-4 \
    --vram-fraction 0.72
python dev/ai_training/evaluate.py --backend ollama --model openbridge-intent-acme-example \
    --data E:/OpenBridgeAI/data_partner_acme --split partner_test --out eval_acme_partner_test.json
```

Between training and evaluation, merge the adapter, convert it to GGUF q8_0 and load it in Ollama exactly like the
official model ([AI_TRAINING.md](AI_TRAINING.md)). Start from the official model's adapter (v4 today), never from
scratch, so the partner model keeps everything the official one knows.

The generator renders every request family that fits each product (about 700 lines for the example), holds whole
templates out for the partner test set, and mixes in a replay slice of the base training set so the adapter keeps
the rest of the home. Training takes one to three hours on one GPU. The adapter is published only if it does at
least as well as the base model on the base test sets and better on the partner test set; the evaluation report goes
with it.

## Example results: the fictional Acme brand (24 November 2026)

Trained from the official v4 model on the example profile (1,485 examples including 800 replayed from the base
set, 186 steps, 1 h 49 min on an RTX 4060 Ti 16 GB, peak 9.7 GB). Same evaluation items for both models:

| Test set | Items | Official model (v4) | Acme adapter |
|---|---|---|---|
| Acme requests held out (`partner_test`) | 71 | 45.1 % | **98.6 %** |
| Home requests written by hand (`home_novel`) | 36 | 97.2 % | 97.2 % |
| Unseen phrasings (`novel`) | 219 | 95.0 % | 95.4 % |
| Household chores written by hand (`chores_novel`) | 17 | 88.2 % | 100 % |

- On Acme requests, wrong or invented actions drop from 38 to 1. The official model failed on Acme product names
  for every family except the vacuum ones ("turn on", "brightness", "undo": 0 %).
- No base test set got worse in accuracy, so the adapter meets the publication rule above. One more wrong action on
  `novel` (9 against 8) is listed in the evaluation report.
- The adapter is an example only: the official model stays `openbridge-intent` (v4).

## What the partner provides, what they get

The partner provides product names, 20 to 50 recorded commands per language (to measure mishearings), and their
usual phrasings. They get the profile, the measured accuracy before and after, and, on a partner plan, the adapter
and its evaluation report (see [Plans](partners/PLANS.md)).
