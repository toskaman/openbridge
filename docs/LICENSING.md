# OpenBridge licensing

OpenBridge has **two licences, with a clear line between them**, plus written licences for partners.

| What | Licence | What you may do |
|---|---|---|
| **The OpenBridge core**: everything in this repository not listed in the next row (runtime, gate, adapters, fabric, apps, UI, AI tooling, docs) | [PolyForm Strict 1.0.0](../LICENSE) | Read, run and test it for **noncommercial** purposes. No modification, redistribution or derivative works. |
| **The integration kit**: [`src/partner_kit.py`](../src/partner_kit.py), every file it generates with `openbridge partner new` (they carry `SPDX-License-Identifier: Apache-2.0`), and the integration guide [`INTEGRATE_YOUR_DEVICE.md`](INTEGRATE_YOUR_DEVICE.md) | [Apache License 2.0](../LICENSES/Apache-2.0.txt) | Use, modify and redistribute, commercially too, keeping the notices. |
| **Your own code**: firmware, SDKs, apps, and the code you write in or around the generated files | **Yours** | Your licence: proprietary, MIT, Apache 2.0... OpenBridge claims no rights over it. |
| **A company trying OpenBridge**: the core, for 90 days, internally | [OpenBridge Evaluation Licence 1.0](../LICENSES/OpenBridge-Evaluation-1.0.md), free, no signature | Install, run and test with your own products, labs and CI; modify internally. No production use, no distribution. |

## What this means for a partner

- **You can build and publish your integration freely.** The adapter, emulator, graph entry, tests and checklist
  that `openbridge partner new` generates are Apache 2.0; what you write in them is yours. You can keep them in your
  own repository, under your own licence, and ship them.
- **Running OpenBridge itself commercially needs a written licence.** The generated code imports OpenBridge core
  modules (for example `src.fabric.contracts`), which stay under PolyForm Strict. Apache 2.0 on the generated code does
  not extend to the core it runs on. Using the core in your QA, CI, customer demos or products is what the
  [partner licence](partners/PARTNER_LICENSE.md) covers.
- **Contributing back:** an integration you send to this repository is accepted under Apache 2.0 for the generated
  parts and the licence you state for your additions; no copyright assignment is asked.
- **Changes to the core** (not to your integration) are made by OpenBridge, or licensed case by case.

## Other permissions and third parties

- A narrowly scoped [hackathon evaluation permission](../HACKATHON_EVALUATION_PERMISSION.md) supplements PolyForm
  Strict so organizers and judges can clone, run, inspect and evaluate the submission.
- Third-party dependencies, SDKs, model weights and services keep their own terms: see the
  [third-party inventory](../THIRD_PARTY.md).
- No licence above grants trademark or branding rights in the OpenBridge name, logo or identity.

## Plans at a glance

Community (free, noncommercial), **Evaluation (free, 90 days, for companies)**, Partner and OEM: what each includes is
on one page, [Plans](partners/PLANS.md). A source-available option that turns each release into Apache 2.0 after two
years is [under consideration](LICENSING_FSL_OPTION.md); it is not applied.

## Commercial & partner licensing

PolyForm Strict covers public, noncommercial use. Companies that want to go further get a separate written
licence. The [partner licence term sheet](partners/PARTNER_LICENSE.md) lists what it covers:

- **Partners get a licence for their integration.** A hardware partner receives a commercial licence to use the
  OpenBridge core with its integration: internally, in its own QA and CI, in demos to customers and, where agreed,
  shipped in its own products or apps.
- **Your code and data stay yours.** OpenBridge claims no rights over a partner's firmware, SDKs, documentation, test
  data or trademarks, and uses them only for that partner's integration.
- **Confidential when you need it.** Work can happen under the partner's NDA. Material shared confidentially stays out
  of the public repository; only what the partner approves is published.
- **Other commercial uses**, such as embedding OpenBridge in a product, deploying it inside a company or
  co-developing a feature, are licensed case by case.

The exact terms are set in a written agreement signed by both parties. This page describes what such an agreement
offers; it is not itself a licence grant for the core. Nothing here is legal advice.

Contact: **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Commercial%20licensing)** ·
[Partner program](partners/README.md) · [Security policy](../SECURITY.md) · [Privacy note](PRIVACY.md)
