# Isolated physical screen-timeout verifier

The participant explicitly authorized testing owned Android devices and reversible changes for this project. Limit the physical verifier to one authorized USB phone and the Android system screen_off_timeout field. No package operations, rooting, firmware changes, security settings or protected-consent bypass.

Bind the adapter to the authorized USB serial internally and a build-fingerprint-derived identity. Never export the serial or fingerprint. Revalidate current ADB authorization and identity before every read/write. Accept only an exact positive integer-second setting representable without conversion loss; otherwise block before writing.

Physical transaction-engine use requires explicit constructor opt-in. Default engines reject physical adapters. HTTP sandbox routes must additionally reject any non-SIMULATED engine even if misconfigured. No physical browser write endpoint is added.

The isolated verifier persists the exact original setting and identity-bound hash before a bounded 30/60-second proposed value. It reads back the applied value independently and always attempts exact restoration in finally. An ambiguous failure remains recoverable in the private journal; external divergence is never overwritten. No automatic reapply after a failure. On restart, an existing active transaction can be recovered without creating another change.

Unit tests must prove fixed commands, value validation, identity/authorization failure, explicit opt-in, and physical-engine refusal by the simulated HTTP route. Complete read-only review before any real write. The physical test may run only with an available authorized owned phone. Public evidence excludes serial, fingerprint, IP, credentials and private device content; success requires actual post-restore measurement.
