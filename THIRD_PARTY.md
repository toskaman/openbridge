# Third-party materials

Inventory reviewed 27 October 2026. No model weights, third-party fonts, downloaded images, or historical application assets are redistributed in this repository. Optional dependencies are installed separately. This inventory is not a legal clearance or a guarantee of compliance; review the exact artifacts and applicable terms before distributing a packaged build.

## Runtime, tools and optional packages

| Material | Use | License / primary upstream reference |
|---|---|---|
| Python 3.14.4 standard library | Application runtime | PSF License and included component notices: https://docs.python.org/3/license.html |
| Browser HTML/CSS/JavaScript APIs | Interface; no external JavaScript library | Browser implementation terms apply to separately installed browsers. |
| Playwright 1.63.0 | Optional development browser verification | Apache-2.0: https://github.com/microsoft/playwright-python/blob/main/LICENSE |
| pyee 13.0.1 | Playwright dependency | MIT: https://github.com/jfhbrook/pyee/blob/main/LICENSE |
| greenlet 3.4.0 | Playwright dependency | MIT / PSF-2.0 licensing and notices: https://github.com/python-greenlet/greenlet/blob/master/LICENSE |
| typing_extensions 4.16.0 | Development dependency | PSF-2.0: https://github.com/python/typing_extensions/blob/main/LICENSE |
| bleak 3.0.2 | Optional PC Bluetooth | MIT: https://github.com/hbldh/bleak/blob/develop/LICENSE |
| winrt-runtime and Windows BLE projections | Optional Windows Bluetooth dependencies; resolve versions from installed environment | MIT: https://github.com/pywinrt/pywinrt/blob/main/LICENSE; record exact installed wheel versions before packaging. |
| Ollama | Separately installed local inference service | MIT code: https://github.com/ollama/ollama/blob/main/LICENSE. Model weights have separate licenses below. |
| Android SDK command-line tools, build-tools 34.0.0, android-34, ADB | Optional Companion build/device tooling | SDK agreement: https://developer.android.com/studio/terms; Android platform-tools distribution includes its own notices. SDK/tools are not redistributed. Companion uses Android framework APIs without third-party libraries. |
| actions/checkout v4, actions/setup-python v5 | CI only | MIT: https://github.com/actions/checkout/blob/v4/LICENSE and https://github.com/actions/setup-python/blob/v5/LICENSE |

Development pins are in `requirements-dev.txt`. These version declarations do not pin all transitive wheel artifacts or browser binaries. If those are bundled later, collect their exact licenses/notices and hashes from the actual distribution rather than treating this source inventory as a binary manifest.

## Optional model weights and hosted services

### Meta Muse Glimmer 30B

Upstream model: https://huggingface.co/meta-models/Muse-Glimmer-30B. Meta explicitly states that **weights** use Apache License 2.0: https://dev.meta.ai/docs/muse-glimmer. This is distinct from Ollama's MIT implementation license. Primary license: https://huggingface.co/meta-models/Muse-Glimmer-30B/blob/main/LICENSE. Primary usage policy: https://huggingface.co/meta-models/Muse-Glimmer-30B/blob/main/USAGE_POLICY.md. Meta's model page also presents that policy as applicable to access/use: https://dev.meta.ai/models/muse-glimmer.

OpenBridge uses separately downloaded `muse-glimmer:30b-q4_K_M` from https://registry.ollama.com/library/muse-glimmer/tags for local advisory explanations and gated proposals. The pinned **registry manifest SHA-256**, not an individual weights-file hash, is `de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1`. Source of pin: `src/ai/glimmer.py`, `config/runtime_models.json`; actual inference evidence: `docs/glimmer-smoke-receipt.json` and `docs/forge/tv-glimmer-live-receipt.json`. No new inference was made for this inventory.

Notice review: upstream root listing reviewed on 27 October 2026 exposes LICENSE and USAGE_POLICY.md; no separate root NOTICE was visible. A metadata-only GET to the existing isolated service on port 11439 subsequently confirmed the installed catalog digest. The installed manifest wraps an original 783-byte registry-manifest blob whose SHA-256 equals the pinned digest; that original manifest lists projector, model and params layers only, with no license or NOTICE layer. No weights were read and no inference was requested. This narrows the packaging uncertainty but does not prove that the model binary lacks embedded notices; see `docs/release/GLIMMER_METADATA_AUDIT.md`. Before redistributing any model artifact, inspect the exact manifest/layers and retain applicable copyright, license and NOTICE material, including Apache section 4 requirements. OpenBridge currently redistributes no weights. Do not apply Llama's license or its attribution phrase to Glimmer as though they were the same license.

### Meta Llama 3.2 3B Instruct

Model `llama3.2:3b-instruct-q4_K_M`; upstream https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct and https://www.llama.com/llama3_2/license/. Llama 3.2 Community License and Acceptable Use Policy apply, separately from runtime code. Copyright © Meta Platforms, Inc. All Rights Reserved. **Built with Llama.** User downloads weights separately; none redistributed here. Pinned registry manifest SHA-256: `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` (`src/ai/local_meta.py`, `config/runtime_models.json`). Receipt: `docs/local-meta-smoke-receipt.json`.

### Hosted Meta and development contributions

Muse Spark 1.3 is a separately hosted service, not shipped weights; its recorded synthetic-only runtime call is `docs/runtime-meta-receipt.json`. Muse Spark visual direction and Muse Wonder 1.0 theme generation are development contributions documented in `CONTRIBUTIONS.md`, `docs/meta-design-receipt.json`, and `docs/forge/meta-web-design-receipt.json`. These services must not be labeled Apache-2.0 simply because Glimmer weights are. Account/service terms and output rights need participant review against the terms accepted for the actual account. The service-terms URL was not verified during this audit; obtain the applicable terms from the authenticated developer account. No new hosted request is authorized by this inventory; fresh promotional-credit confirmation is required first.
