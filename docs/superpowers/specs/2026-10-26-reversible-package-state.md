# Reversible optional-app state (physical)

The screen-timeout write was refused by the owned phone, so this follows ARCHITECTURE_FRESH_BUILD's alternative: disable then re-enable one preselected optional app for Android user 0 only.

Scope: a reviewed allowlist of data-preserving utility apps (ruler, stopwatch, compass). Never system, security, messaging, banking or Google services. Fixed commands only: `pm disable-user --user 0`, `pm enable --user 0`, `pm default-state --user 0`.

State is the exact Android user-0 COMPONENT_ENABLED_STATE code (0 default, 1 enabled, 3 disabled-user) read from dumpsys and cross-checked against `pm list packages -e/-d`; disagreement blocks. Undo restores the exact original code, not merely "enabled". Each read and write re-checks USB authorization and build identity. The durable transaction engine accepts only the adapter's declared targets; package targets cannot be used with the timeout adapter or vice versa.
