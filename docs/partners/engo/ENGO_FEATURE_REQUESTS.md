# Suggestions for ENGO: what OpenBridge would need from the glasses

*Living document, kept up to date by the OpenBridge project. Last update: 2026-11-26 18:45 (Paris).*

OpenBridge drives an **ENGO 3 Photochromic** through the phone's Bluetooth: menus, messages, TV and vacuum control,
sport screens and an AI assistant answering questions spoken into the phone. Everything below was found while
building and wearing it. Each request says what we saw, why it matters to wearers, and the smallest change that
would unlock it. Nothing here is a complaint: the glasses are light, readable and reliable. These are the missing
pieces between "a display" and "a hands-free interface".

**Résumé en français.** La seule entrée des ENGO 3 aujourd'hui est le double tap sur la branche, vu comme un seul
évènement. Nos demandes principales : remonter le nombre de taps (1, 2, 3), un appui long et un glissement le long de
la branche ; des polices avec accents ; une police plus petite ; la zone visible et l'orientation documentées ; deux
connexions Bluetooth à la fois (application ENGO + OpenBridge). Le détail, avec nos mesures, est ci-dessous.

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

With one event, a menu can only move forward. Opening and going back need the phone (buttons or voice) or a timer,
which is slow and not hands-free.

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

## How this list is kept

Every time OpenBridge needs something the glasses cannot do, it is added here with what we measured, and the
[What's new](../../../README.md#whats-new) log mentions it. Items move to a "Done" section when a firmware or SDK
release delivers them, with the version.

## Done

*(Nothing yet.)*

Evidence: [ENGO 3 through the phone, 26 Nov 2026](../../evidence/engo3-phone-link-26nov.md) ·
[display facts](../../GLASSES.md#display-facts-measured-on-a-real-engo-3-26-november-2026)
