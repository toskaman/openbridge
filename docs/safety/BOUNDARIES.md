# Safety and model boundaries

RuntimeModelBroker pins Meta Muse Spark 1.3 to the official Meta HTTPS endpoint. A supervised call through this application core succeeded on 26 October 2026 using synthetic fixture facts; docs/runtime-meta-receipt.json records the returned identity, request ID, token use and estimated cost. The live browser inference endpoint is implemented and tested with controlled responses, but no live browser-to-provider session is claimed.

Default startup has no credential or free-credit permit and makes no cloud calls. A short-lived supervised credit observation is required for explicit requests. Unknown models, malformed proposals, unknown evidence, expired observations and exhausted durable allowances fail closed. See FREE_CREDITS.md for limits and account-wide verification limitations.

Physical Android and Freebox facts stay local. The model receives only the synthetic demo allowlist. Output is advisory text with action=inspect_only; no model response is passed to ADB, a router or a command shell. A key is never served to the browser. The one-shot PowerShell 7 verifier passes the encrypted local credential to its child process only through standard input.

Physical writes are limited to the consent-gated agent (one allowlisted optional app state, exact restoration, journal recovery) and the session restore of OpenBridge's own changes. A separate explicit-opt-in timeout verifier was tested once and Android refused the operation; original-state preservation was verified, but physical change/Undo success is not claimed. Future changes require consent, an exact state snapshot, deterministic checks, independent read-back and verified restoration. No credentials, serial numbers, network identifiers or private device dumps belong in public evidence.
