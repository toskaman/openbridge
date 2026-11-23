# Support policy

What is supported, for how long, and how to get help. [Version française](#version-française).

## Releases

OpenBridge follows `MAJOR.MINOR.PATCH`. Until 1.0, a minor release (0.5, 0.6...) may change commands, file formats
or the Companion protocol; every such change is listed in the [changelog](../CHANGELOG.md) with what to do.
Releases are **demos**: they are not yet the final version with the dedicated model fully wired in.

| Version | Status | Security fixes |
|---|---|---|
| **0.5.x** (current) | supported | until 3 months after 0.6.0 |
| 0.4.x | end of life on 23 February 2027 | critical fixes only, until then |
| 0.3.x and older | end of life | none: please upgrade |

Fixes land on `main` first, then in a patch release. A partner or OEM agreement can add a maintained branch for the
versions it ships, for the agreed period (see [Plans](partners/PLANS.md)).

## Platforms

| Platform | Level |
|---|---|
| Windows 10 and 11, x64 ([ready-to-run download](https://github.com/toskaman/openbridge/releases)) | supported, tested in CI and on the author's PCs |
| Linux and macOS, from source (Python 3.14.4) | supported for the core and the command line, tested in CI; hardware integrations vary |
| Android Companion 0.13.0 (phone, Android TV, Wear OS) | supported; 0.10 to 0.12 still pair with a warning (no CPace) |
| Home Assistant (REST API, long-lived token) | supported, current stable releases |
| Local models through Ollama | supported; models and Ollama are installed separately |

## Getting help

| Channel | For | Response |
|---|---|---|
| [GitHub issues](https://github.com/toskaman/openbridge/issues) | bugs, questions, device requests | best effort |
| [Security policy](../SECURITY.md) | vulnerabilities (private reporting) | acknowledged within 72 hours |
| [info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Support) | evaluation licence holders | best effort, by email |
| Agreed channel | partner and OEM plans | response times set in the agreement |

OpenBridge is built by an independent developer: there is no 24/7 service. A bug report helps most with the command
you ran, `openbridge doctor --json`, and the receipt of the action that went wrong (receipts hold no secrets).

## What "supported" does not mean

No warranty: the [licence](../LICENSE) and the [evaluation licence](../LICENSES/OpenBridge-Evaluation-1.0.md) say so.
OpenBridge refuses dangerous actions (unlocking doors, garage doors, alarms, firmware) by design; it is not a safety
or security system and must not be used as one.

---

## Version française

- **Versions** : 0.5.x est maintenue (correctifs de sécurité jusqu'à 3 mois après la 0.6.0) ; 0.4.x reçoit les
  correctifs critiques jusqu'au 23 février 2027 ; les versions plus anciennes ne sont plus maintenues. Les versions
  publiées sont des **démos**, pas encore la version finale avec le modèle dédié.
- **Plateformes** : Windows 10/11 x64 (téléchargement prêt à l'emploi), Linux et macOS depuis les sources, Companion
  Android 0.13.0, Home Assistant, modèles locaux via Ollama.
- **Aide** : issues GitHub (au mieux), politique de sécurité (accusé de réception sous 72 h), e-mail pour les
  licences d'évaluation, canal convenu pour les partenaires et OEM.
- **Aucune garantie**, et OpenBridge n'est pas un système de sécurité.
