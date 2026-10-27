# Glimmer installed metadata audit

27 October 2026; metadata inspection only. No inference, loading, release, download or model-process change requested. `dev/forge_glimmer_cpu_service.py` selects the existing private Glimmer store and binds its isolated service to `127.0.0.1:11439`, with cloud disabled and inherited environment restricted.

GET `/api/tags` on that endpoint returned `muse-glimmer:30b-q4_K_M`, digest `de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1`. The local installed manifest is an Ollama wrapper, SHA-256 `47047bcde318d0d3b14b647bf85df60529b75195cf1400c43b892955fe6d3d47`, and references the original 783-byte registry manifest as a manifest layer. That original metadata blob hashes exactly to the pinned digest above.

| Original manifest layer | Bytes | Digest |
|---|---:|---|
| projector | 1400328928 | `sha256:f48b452316f9b213758e8659444029b961a24a07f99a1abb2a9f88b06f7c00c6` |
| model | 16756681056 | `sha256:71b5c9c9abbc2a9e7c13550b6f9fe1f062650117a24490b15a310cbd7de03f8b` |
| params | 42 | `sha256:56380ca2ab89f1f68c283f4d50863c0bcab52ae3f1b9a88e4ab5617b176f71a3` |

No explicit license or NOTICE layer exists in this original manifest. Large layer contents were not inspected or hashed in this audit; values above are manifest declarations, not newly recomputed weight-file checksums. No `/api/show` request was sent: the catalog plus local metadata supplied the required bounded inspection.

[Meta documentation](https://dev.meta.ai/docs/muse-glimmer) explicitly licenses the weights under Apache-2.0; [upstream LICENSE](https://huggingface.co/meta-models/Muse-Glimmer-30B/blob/main/LICENSE) and [USAGE_POLICY.md](https://huggingface.co/meta-models/Muse-Glimmer-30B/blob/main/USAGE_POLICY.md) remain the primary references. Upstream root listing had no separate NOTICE visible when reviewed. Absence of a manifest license layer does not negate the published license or establish complete notice compliance. No model weights are redistributed; review exact artifact and notices before changing that boundary. Ollama MIT code license remains separate.
