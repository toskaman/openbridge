# P30 Glimmer synthesis (30 Oct 2026, REAL_HARDWARE bundle)

Two Meta Muse Glimmer 30B capabilities generated from the live phone
evidence bundle, forge-validated, published to obv4.1 manifests, revoked.

- Model: muse-glimmer:30b-q4_K_M, :11438, digest
  de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1 (verified).
- Prompt: v4-synth-5. Bundle: value-free (opaque ids + fact descriptors).
- cap-bbd643db0267: "Show phone battery and storage on a simple card",
  chain read_facts + visual_readback, grants [read], 2 evidence refs.
- cap-18904cbf7bae: "Show AVD battery level as a card", first attempt.
- Each: attempt 1 pass, manifest digest recorded, then revoked.
- Honest path: 8 v4 rejections (opaque-prefix copy) fixed the prompt, not
  the validator; 3 v4-synth-5 rejections were a CLI harness bug
  (model_run_id ordering), fixed to match synthesize().
- Llama 3.2 3B: 0/1 on the long contract (non-JSON), recorded negative.
- Staging: published-pending-kernel (substrate kernel PR unmerged).
