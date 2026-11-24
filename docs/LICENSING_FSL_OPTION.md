# Option under consideration: a source-available core that becomes open source after two years

> **Decision (24 November 2026): not adopted.** The owner keeps PolyForm Strict 1.0.0; this page is kept for reference.
>
> **Status: proposal, not applied.** The core is licensed under PolyForm Strict 1.0.0 today. Changing it is the
> owner's decision and is hard to undo: every version published under the new licence becomes Apache 2.0 two years
> after its release, for everyone, forever. Have it reviewed by counsel before deciding.

## The proposal

License each new core release under the **Functional Source License, version 1.1, with Apache 2.0 as the future
licence** (`FSL-1.1-Apache-2.0`, published by Sentry and used by several infrastructure companies).

| | PolyForm Strict (today) | FSL-1.1-Apache-2.0 (proposal) |
|---|---|---|
| Read the source | ✅ | ✅ |
| Use internally in a company, including commercially | ❌ (needs a licence) | ✅ |
| Modify, contribute fixes | ❌ | ✅ |
| Offer a competing product or service built on OpenBridge | ❌ | ❌ for two years |
| What happens later | nothing | each release becomes **Apache 2.0** two years after it ships |
| Recognised by companies' legal teams | rare | widely known; used by Sentry, Codecov and others |

## Why it helps partnerships

- Engineers can try and use OpenBridge at work without legal approval: the evaluation licence becomes unnecessary
  for internal use.
- Contributions from partners become possible (today the core cannot be modified by anyone else).
- Partners know the code they depend on cannot disappear: in the worst case, it becomes Apache 2.0.

## What it costs

- Anyone may use the core commercially **internally** for free, so revenue must come from what FSL still protects
  (competing products and services), from OEM distribution rights, from services (integrations, audits, voice models,
  benchmarks) and from support.
- Releases older than two years can be used by anyone, competitors included.

## What would change in the repository

1. `LICENSE` becomes the FSL-1.1-Apache-2.0 text with the licensor and the "Competing Use" definition adapted to
   OpenBridge (a product or service that offers device orchestration, verification or AI device control to third
   parties).
2. `docs/LICENSING.md` and the partner pages are updated; the evaluation licence is kept for older releases.
3. Releases published under PolyForm Strict stay under PolyForm Strict; only new releases change.

Decision and questions: **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Licence)**.
