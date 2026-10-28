# Workspace layout and maintenance

| Location | Purpose |
|---|---|
| `src/` | Application, runtime, adapters and interface |
| `companion/` | Android Companion source and build files |
| `tests/` | Unit, contract, integration and browser checks |
| `dev/`, `scripts/` | Maintained CLI, launch, build and evaluation tools |
| `config/`, `.github/` | Runtime model configuration and CI |
| `docs/` | [Documentation index](README.md), current checklist and evidence |
| `docs/archive/` | Consolidated historical checkpoints |
| `artifacts/` | Ignored local runs, screenshots, receipts and temporary outputs; evidence may exist only here |
| `dist/` | Ignored release packages; retain while needed for distribution or provenance |

## Cleanup

Before changing or deleting existing targets, create a targeted ZIP under `D:/DevBackups/OpenBridge/OpenBridge_YYYY-MM-DD_HH-mm-ss.zip`. Include only affected files, record paths/checksums and purge matching archives older than 90 days. Resolve deletion targets and ensure they remain inside this project. Do not clean sibling projects, live journals, credentials, budget ledgers or model caches.

Python bytecode (`__pycache__`, `*.pyc`) and `.pytest_cache` are disposable and regenerate. Superseded local PR message drafts and resume notes may be removed after their purpose is covered by the team board/GitHub and no tracked file references them; retain their targeted backup.

Lack of import references does not prove dead code: many `dev/` tools are standalone commands. Preserve active source, release packages, original evidence and failed attempts, model provenance, frozen inputs/gold/prompts/checksums, licenses and CI assets unless a specific dependency review supports removal. Do not use a broad `git clean -fdx` or delete the whole artifacts folder.

## Consolidated status paths

The former `docs/REMAINING_WORK.md`, `docs/forge/WORK_STATUS.md` and `docs/jury/STATUS.md` are consolidated with earlier release snapshots in [the checkpoint archive](archive/RELEASE_CHECKPOINTS.md). Their current responsibilities belong to [release status and remaining work](RELEASE_STATUS.md). Links were migrated instead of keeping duplicate status pages.
