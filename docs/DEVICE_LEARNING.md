# Devices that learn and talk to each other

OpenBridge now learns from every action it runs, suggests new features built only from what your home has
proven, and lets one device trigger another, through the same consent and read-back gate as everything else.

## 1. Learning: `openbridge learn report`

Every receipt (verified, blocked, failed, with its latency) is folded into a profile per device:
success rate, p50/p95 latency, states seen, value ranges. An action is **proven** once it ran at least 3 times
with 80 % or more verified read-backs. Device keys are derived from the pseudonymized identifiers, so what
OpenBridge learns survives restarts. Stored locally in `%LOCALAPPDATA%\OpenBridge\device_learning.json`;
`openbridge learn reset --consent ALLOW` forgets it.

## 2. New features: `openbridge create suggest`

OpenBridge combines proven capabilities into cross-device features (Cinema mode, Intermission, Quiet while
cleaning, Leaving home, Lights out...). A suggestion is **high** confidence when the trigger state was really
observed on that device. Nothing is created automatically.

## 3. Links: devices that talk to each other

```
openbridge links add --when media_player.living_room --state playing \
                     --then light.ceiling_lights --action set_brightness --value 20 --title "Cinema mode"
openbridge links approve LINK_ID --consent ALLOW
openbridge links watch --seconds 60
```

A link fires only on a real state change (never on the first snapshot), only once approved, and every firing is
a normal typed action: consent, allowlist, read-back, receipt. Guards: per-link cooldown, a cap per hour, and a
chain guard (an action caused by a link cannot trigger another link for 10 s), so two links can never loop.
Only reversible or harmless primitives are allowed (`ha_set`, `ha_command`, `tuya_command`, `tv_wake`,
`tv_sleep`); door, garage and alarm policies still apply.

## 4. Long test: `openbridge ha soak`

`openbridge ha soak --cycles 20 --consent ALLOW` runs every allowed action on every controllable device, in a
random order, many times, and undoes each change. Covers are skipped unless `--include-covers`.

Results on a real Home Assistant (demo devices), 22 November 2026: [evidence](evidence/device-learning-soak-22nov.md).
