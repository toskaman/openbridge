# Skill packs

A skill pack is a set of ready-made [skills](SKILLS.md) that make devices of different brands work together, installed
in one command. A pack never names anyone's devices: it names **roles** ("a robot vacuum", "a TV or speaker") and each
role accepts device categories. When you install a pack, each role is mapped to one of your devices, each step is
resolved for that device's brand (a Roborock through Home Assistant and a Tuya robot take different commands), and the
skills are saved **unapproved**. You read them, approve the ones you want, and from then on they run with no AI model.

```
openbridge skills packs --lang fr
openbridge skills install-pack quiet-cleaning --map robot=vacuum.kitchen
openbridge skills list
openbridge skills approve skill-1a2b3c4d --consent ALLOW
```

A role with exactly one possible device is mapped automatically; otherwise the command lists the candidates and asks
for `--map ROLE=ENTITY`. A pack is installed whole or not at all.

## Packs shipped with OpenBridge

| Pack | Roles | What it does |
|---|---|---|
| `cinema` | TV or speaker, dimmable light | The light dims when a film plays and comes back up on pause; a "Movie night" button |
| `leaving-home` | light or plug, TV or speaker, robot vacuum | "I'm leaving": lights and TV off, the robot starts. "I'm home": light on, robot docks |
| `quiet-cleaning` | media player, robot vacuum | The robot pauses as soon as the TV or speaker plays |
| `good-morning` | thermostat, dimmable light, blinds | Weekday and weekend wake-up: heating, soft light, then the blinds open |
| `good-night` | TV or speaker, light or plug, door lock | One button: TV off, light off, door locked (OpenBridge never unlocks) |
| `energy-saver` | dimmable light, standby plug | "Eco evening": light to 30 %, plug off; plugs cut again nightly at 1:00; "Back to full light" restores 80 % |

Every pack is in French and English.

## Safety

A pack adds no power. Its steps can only use the primitives allowed in a skill, every run goes through the executor
(schema, policy refusals, consent, read-back, receipt), and nothing runs before you approve it. Steps that cannot be
undone (start a robot, open blinds, lock a door) come last in every shipped pack, because a run stops at the first step
that is not verified.

Packs shipped with OpenBridge are pinned: `src/runtime/packs/INDEX.json` holds the SHA-256 of each file, and a file
changed after review is not listed. The test suite fails if a pack and its pin disagree.

## Partner packs

A partner pack shows the partner's device working with other brands, the way a shareable routine does, but locally and
with read-back. It uses the same format with `"publisher": {"name": "...", "kind": "partner", "url": "..."}`.

1. Write the pack (format below). Prefer roles that accept several categories, so the pack works in more homes.
2. Run `openbridge skills pack-check acme-cinema.json`. It reports shape errors or prints the id and SHA-256.
3. Send the file. After review it goes into `src/runtime/packs/`, `INDEX.json` is regenerated with
   `skill_packs.build_index()`, and the pack ships in the next release. Partner plans include this (see
   [Plans](partners/PLANS.md)).

```json
{"format": "openbridge-skillpack/1", "id": "acme-cinema", "version": "1.0.0",
 "title": {"en": "Acme cinema", "fr": "Cinéma Acme"},
 "description": {"en": "...", "fr": "..."},
 "publisher": {"name": "Acme Lighting", "kind": "partner", "url": "https://example.com"},
 "roles": {"tv": {"categories": ["media_player"], "label": {"en": "A TV or speaker", "fr": "Une TV ou enceinte"}},
           "light": {"categories": ["light"], "label": {"en": "An Acme light", "fr": "Une lumière Acme"}}},
 "skills": [{"name": {"en": "Dim on play", "fr": "Tamiser à la lecture"},
             "trigger": {"kind": "state", "device": "@tv", "state": "playing"},
             "steps": [{"device": "@light",
                        "by_category": {"light": {"primitive": "ha_set",
                                                  "params": {"action": "set_brightness", "value": 15}}}}]}]}
```

Rules checked by `pack-check`: 1 to 8 roles, 1 to 12 skills, each step lists what to do for every category its role
accepts that it supports, only skill primitives, and once resolved each skill must be a valid skill (1 to 8 steps, a
state-triggered skill never acts on its own trigger device).
