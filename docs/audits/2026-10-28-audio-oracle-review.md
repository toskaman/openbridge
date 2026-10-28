# Audio oracle review — 28 October 2026

PR85 exact head089c39f3803fc1a25a40ed6b719b04ad6789d4ad introduces the missing generic STREAM_MUSIC state read-back. Five parser/registry tests independently pass. Three additional negative checks pass: no music stream, unknown muted token, and a neighbouring stream's muted flag all remain muted=null/readable=false. No neighbour-state guess is admitted.

[Immutable source-hashed receipt](audio-oracle-089c39f.json). Reproduce with `python -B -m dev.audit_v4_audio --output <NEW_PATH>`. Exact AndroidActions/registry/test Git blobs loaded in fresh in-memory modules; other dependencies from audit checkoutd470b57. No driver import, HTTP, ADB, device operation, provider, Vault or spend.

## Closure scope

The previous absence of an audio-state primitive is addressed at this proposed source revision. The descriptor correctly limits this to Android's reported media-stream state, not HDMI-CEC/AVR state or an independently measured audible signal. Unknown parsing remains unknown. Merge/release approval is separate from this parser review.

The supplied hardware transcript reports false/20 -> true/0 -> false/20, and its three audio read objects have equal first/last state. This is contributor-recorded evidence, not a physical result independently observed by this audit. All shown Executor states are EXECUTED; do not silently relabel them VERIFIED. Retain source revision, exact device/route, consent scope and raw dumps/receipt provenance when advancing physical acceptance. An audio-state read improves the oracle; it does not prove runtime Meta creation or unseen task novelty.

The historical hardware driver has top-level actions, selects the first TV and toggles twice without guarded compensation. Never import/replay it as an audit helper or assume a second toggle always restores state under failure/external changes. Preserve the original driver/transcript as evidence. Any future attended driver should bind the exact approved fingerprint, check initial/read-back states, stop on unknown/error, journal uncertainty and explicitly confirm restoration without blind retries.

## Remaining gates

- PR78 live allowance ledger override restriction and regression. Latest review records contributor-reported owner decisions on a24h eval backstop and separate envelopes; this audit neither changes those policies nor treats the report as a fresh credit balance. The unrestricted override finding is unchanged atd49d7a9.
- Runtime end-to-end generation, deterministic compile/sandbox, bound owner grant/install/invoke, independent read-back, revoke/restart and cleanup.
- Genuine unseen-task/oracle freeze and competent rules/library ablation. Public TV-mute fixtures are integration cases, not held-out gold.
- G3/submission-plan corrections already posted on PR83; text-only180-second draft exists in this audit. No video or recording without a new explicit owner request.
- Exact loaded runtime revision, final claims review and submission receipt.

Release remains BLOCKED. No existing production/protected/frozen/historical files were modified. New audit artifacts only; no targeted existing-file backup was needed.
