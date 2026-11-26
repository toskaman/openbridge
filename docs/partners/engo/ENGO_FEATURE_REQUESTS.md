# Suggestions for ENGO: what OpenBridge would need from the glasses

*Living document, kept up to date by the OpenBridge project. Last update: 2026-11-26 20:30 (Paris).*

OpenBridge drives an **ENGO 3 Photochromic** through the phone's Bluetooth: menus, messages, TV and vacuum control,
sport screens and an AI assistant answering questions spoken into the phone. Everything below was found while
building and wearing it. Each request says what we saw, why it matters to wearers, and the smallest change that
would unlock it. Nothing here is a complaint: the glasses are light, readable and reliable. These are the missing
pieces between "a display" and "a hands-free interface".

**Résumé en français.** La seule entrée des ENGO 3 aujourd'hui est le double tap sur la branche, vu comme un seul
évènement, et il met environ **2 s** à être pris en compte. Nos demandes principales : remonter le nombre de taps
(1, 2, 3), un appui long et un glissement le long de la branche ; **réduire la latence et le debounce du tap** ; des
polices avec accents ; une police plus petite ; la zone visible et l'orientation documentées ; deux connexions
Bluetooth à la fois (application ENGO + OpenBridge). Ces points sont dans le firmware des lunettes : OpenBridge peut
tester immédiatement toute build candidate sur la vraie paire. Le détail, avec nos mesures, est ci-dessous.

> **Partenariat.** Ces demandes portent sur le firmware fermé des ENGO 3 (voir « Firmware et livraison » en bas).
> OpenBridge est partenaire officiel d'ENGO et peut valider chaque build sur le matériel réel, avec preuves publiques.

## Priority 1: input

The ENGO 3 has one input today. Measured on our pair on 26 Nov 2026 (gesture sensor enabled with commands `0x20 = 1`
and `0x21 = 1`, notifications on the gesture and touch characteristics):

| Action on the glasses | What OpenBridge receives |
|---|---|
| Single tap on the temple | nothing |
| Double tap | one gesture event, value `01` |
| Triple tap, quadruple tap | one gesture event, value `01` (same as a double tap) |
| Hand wave in front of the lens (ENGO 2 gesture) | nothing |
| Touch characteristic (`...cbc`) | no notification at all |
| Time from the double tap to the event reaching OpenBridge | about **2 s** |

With one event, a menu can only move forward. Opening and going back need the phone (buttons or voice) or a timer,
which is slow and not hands-free.

**The ~2 s is in the glasses, not in OpenBridge.** On our side a tap is turned into an action in under 100 ms (the
phone relay wakes the PC as soon as the gesture notification arrives, and the UI redraws within 50 ms). The delay and
the way 3-4 taps collapse into one event are the firmware's own tap detection (a debounce window before it emits).
A shorter window, or the raw per-tap events, would remove both at once.

| # | Request | Why it matters | Suggested change |
|---|---|---|---|
| I1 | **Report the number of taps**: 1, 2, 3 as different values | Next / open / back without touching the phone | Gesture event value = tap count (`01`, `02`, `03`), or one event per tap with a timestamp |
| I2 | **Single tap as an event** | The most natural "next" or "OK" | Send it, at least when a third-party app has enabled gestures |
| I3 | **Long press** (tap and hold) | "Back" or "home" with no ambiguity | A distinct value, e.g. `10` |
| I4 | **Swipe along the temple**, forward and backward | Scroll lists, change pages of long text, volume up / down | Two values (forward, backward) if the touch area allows it |
| I5 | **Hand wave on the ENGO 3**, like the ENGO 2 | Hands-free when wearing gloves (cycling, ski, work) | Same event as the ENGO 2, if the sensor is present |
| I6 | **Head gestures** (nod, shake), if an IMU is fitted | Confirm / cancel when hands are busy | Event values for nod and shake |
| I7 | **Document the touch characteristic** | We subscribed and got nothing; we don't know what it is for | One paragraph in the SDK docs |
| I8 | **Let the app choose the tap window** | Fast users vs gloves | A command setting the multi-tap timeout |
| I9 | **Cut the tap-to-event latency** (about 2 s today) | The HUD should react as fast as a watch | A shorter debounce, or emit each tap as it happens and let the app group them |

## Priority 1: text

| # | Request | Why it matters | Suggested change |
|---|---|---|---|
| T1 | **Accented characters** (é è à ù ç ô, « », €, °) | French, German, Spanish… messages show as "ete" instead of "été"; ° and € disappear | Latin-1 or a Latin Extended subset in the system fonts |
| T2 | **A smaller font** (16-18 px line height) | The smallest system font is 24 px: a message preview fits about 22 letters | One more system font |
| T3 | **Font metrics in the docs** | We measured 24 / 24 / 38 / 64 / 75 / 82 px line heights and about h/2 per letter by trial | Table of line height and advance per font id |

Custom fonts can be uploaded today, but each app would have to ship its own; a shared accented font in the
firmware helps every developer.

## Priority 2: display

| # | Request | Why it matters | Suggested change |
|---|---|---|---|
| D1 | **Document orientation and text anchoring** | On our ENGO 3 both axes are mirrored and upright text needs rotation 4, anchored at its top-left; we found this by testing | One diagram in the SDK docs, or a command to set the origin at the top-left |
| D2 | **Visible area per model** | We measured x 0 to ~292 and y 0 to ~236 of the 304 x 256 panel; text at the edge is cut | Publish it, or a command returning it |
| D3 | **Arc angles** | Device angles equal logical angles once both axes are mirrored; start must be 0-359, end = start + sweep | Document it |
| D4 | **Colour names** | We use the official 81-value red-green palette; named values (green, orange, red...) in the docs would save trial | A short table of tested colours |

## Priority 2: connection

| # | Request | Why it matters | Suggested change |
|---|---|---|---|
| C1 | **Two connections at once** (ENGO app + one third-party app) | Today the ENGO app must be closed before OpenBridge connects | Allow a second central, or a hand-over command |
| C2 | **A capability query** | One command returning firmware version, gesture types, fonts, colour support and visible area lets an app adapt to every model | Extend the existing settings / info commands |
| C3 | **Public firmware changelog** | Know when a new gesture or font arrives | A page or a field in the SDK repository |

## Later generations (hardware wishes)

| # | Wish | Why |
|---|---|---|
| H1 | A touch strip with swipe on both temples | Rich navigation without the phone |
| H2 | A microphone, or a documented way to use the phone's | "Ask the glasses" without taking the phone out |
| H3 | A white or blue channel | Neutral text and an information colour next to green / orange / red |

## Firmware and delivery

Everything in "input" and "text" above lives in the glasses' firmware, which is closed:

- The ActiveLook SDK updates firmware only through the signed over-the-air service
  (`https://fw.activelook.net/v1/firmwares/{hardware}/{token}`, one token per account); the glasses verify the image
  before installing. There is no BLE command to read the running firmware, and the documented command interface has
  no tap-sensitivity or debounce setting. So an app cannot change tap behaviour from its side, and OpenBridge does not
  try to read or alter the signed firmware.
- To deliver these, the smallest paths are, in order of least effort for ENGO/Microoled:
  1. a firmware build that **emits each tap as a separate event** (with a timestamp or a per-burst count) and drops
     the debounce — the app then decides what 1 / 2 / 3 taps and a long press mean, so future changes need no new
     firmware;
  2. failing that, specific new events for single tap, long press and swipe, plus a command to set the tap window;
  3. for OpenBridge's own validation, a **source or toolchain arrangement** under the partnership, or candidate signed
     builds we flash over the official OTA path.
- **What OpenBridge brings:** we have the real ENGO 3 pair on a working bridge and can test any candidate build the
  same day, on real hardware, and publish a verified report (as we do for every device). A new gesture or font can be
  confirmed within hours of a build landing.

Contact: through the ENGO partnership channel (official partnership agreement on file; mirrored in the OpenBridge
GitHub). Happy to join a call with the firmware team and walk through the measurements.

## How this list is kept

Every time OpenBridge needs something the glasses cannot do, it is added here with what we measured, and the
[What's new](../../../README.md#whats-new) log mentions it. Items move to a "Done" section when a firmware or SDK
release delivers them, with the version.

## Done

*(Nothing yet.)*

Evidence: [ENGO 3 through the phone, 26 Nov 2026](../../evidence/engo3-phone-link-26nov.md) ·
[display facts](../../GLASSES.md#display-facts-measured-on-a-real-engo-3-26-november-2026)
