# ENGO glasses: messages, TV, vacuum, voice and sport

OpenBridge puts a small, calm interface on ActiveLook / ENGO glasses (ENGO 1, 2 and 3, including ENGO 3
Photochromic): your messages, a TV remote, the robot vacuum, voice commands from the phone's microphone, and a sport
mode (running, cycling, intervals, Ghost, GPX navigation). In French or English.

![Every glasses screen, rendered by HUD Studio](img/glasses_contact_sheet.png)

## How it fits together

```
phone (OpenBridge Companion) --messages, voice-->  PC: openbridge glasses run  --frames-->  glasses (Bluetooth) or HUD Studio
                                                    |
                                                    +--typed actions through the gate--> TV (ADB), robot vacuum (Tuya)
```

- **Messages:** the Companion app reads the notifications of the apps you allow (Discord, Telegram, SMS, Google
  Messages, Samsung Messages; WhatsApp and Signal on request) once you grant notification access in Android
  settings ("Messages on my glasses" button). The PC fetches them over the paired, encrypted relay. They stay in
  memory (last 50), are never written to disk and never answered on your behalf. Privacy mode: show the text, only
  the sender, or nothing.
- **TV:** volume, app switching (YouTube, Netflix, Prime Video, Disney+, Spotify, Plex, Twitch, myCANAL, VLC, Kodi),
  a full remote (arrows, OK, back, home, play/pause) and sleep / wake, on an Android TV / Google TV linked over ADB.
  The glasses show the volume and the app on screen, read back from the TV.
- **Vacuum:** start, pause, back to dock, find (beep).
- **Voice:** hold the mic in the Companion app and speak, in French or English. The phone records, the PC transcribes
  locally, OpenBridge's own command model understands ("baisse le son de la télé", "start the vacuum"), and the
  glasses show what was heard and what was done. Anything the glasses may not do is refused and said so.

## A PC without Bluetooth: the phone holds the link

```
openbridge glasses run --link phone             # the paired phone's Bluetooth talks to the glasses
openbridge glasses run --link phone --mirror    # ... and HUD Studio on the PC shows the same frames
```

The paired OpenBridge Companion (0.14.0 or later) connects to the glasses itself (relay operations
`glasses_connect`, `glasses_write`, `glasses_events`, `glasses_disconnect`); the PC sends the ActiveLook frames over
the signed, encrypted relay channel (USB or Wi-Fi) and gets the gestures back. Scope, by construction: only a device
exposing the ActiveLook service is kept connected, the PC can only write the ActiveLook RX characteristic, and
unpairing drops the link. Close the ENGO app first: the glasses accept one connection at a time.

**Oracle from the phone microphone:** open the Oracle screen in the Companion and speak. Phones with an Android speech
service transcribe on the phone; phones without one (seen on a Blackview BV9300 Pro) record short utterances and the
PC transcribes them locally, then answers with the Oracle and shows the answer on the glasses. Long answers are cut
into pages in the large font; one wave shows the next page.

**The Oracle is an optional module, per Companion.** Switch it off and the Oracle button disappears from that phone or
watch; switch it back on the same three ways:

- on the PC, in **Controls** (the Companions customisation screen), **Modules** box of the selected screen;
- `openbridge glasses module oracle on|off [--relay <relay id>]`;
- by typing or saying it on the Companion: "active l'Oracle", "retire l'Oracle", "turn off the Oracle"
  (matched without any model; speech-to-text near-misses such as "Loracle" are accepted).

The switch is stored on the device (relay operation `set_modules`, Companion 0.14.0 or later) and confirmed back to
the PC.

**Companion 0.15:** six modules instead of one (Oracle, Messages, Sport, TV, Vacuum, Phone sensors); a module
switched off on the phone hides its menu on the glasses within 15 s. The Companion also shows a live copy of the
glasses' screen, takes the volume keys as next / back, sends the phone's GPS and Bluetooth sport sensors to the sport
screens when the owner allows it, and can drive the glasses alone when the PC is away (standalone mode). Details:
[Android Companion](ANDROID_COMPANION.md#0150-27-november-2026).

## Wear OS watch: full ENGO 3 controls on the fly (ENGO × ActiveLook by Microoled)

When a Wear OS watch running OpenBridge Companion (`android.hardware.type.watch` / `form_factor: watch`) is detected,
every ENGO 3 hardware and HUD control fits cleanly on the watch across four `<= 12`-control pages (`main`, `screens`,
`display`, `align`), each carrying a live status header tile and routed through OpenBridge's signed `RemoteControls` +
`Router` + `Executor` channel (`engo_control` skill):

- **Covered controls:** navigation (`next`, `ok`, `back`, `home`, D-pad), all 9 HUD screens (`home`, `inbox`, `oracle`,
  `voice`, `sport`, `tv`, `vacuum`, `calibration`, `settings`), BLE display power (`0x00`), brightness (`0x10`), ALS auto-luma
  (`0x22`), temple tap/gesture enable (`0x21`), OLED clear (`0x01`), optical alignment shift (`0x09`), 180° rotation,
  privacy mode, language (`FR`/`EN`), units (`metric`/`imperial`) and inbox clear.
- **Zero clutter when no watch is paired:** the watch button in Companion (`ENGO 3 Controls`) only renders on
  `watch` hardware, and the PC Web UI (`Controls` and `Settings`) hides the watch panel whenever
  `GET /api/v2/engo_watch_controls` reports `watch_detected: false`.
- **On-the-fly activation:** ask by text or voice in French or English (from the watch, phone or PC Ask OpenBridge — e.g.
  `"affiche tous les contrôles ENGO 3 sur ma montre"`, `"affiche les réglages de la ENGO 3 sur la montre"`,
  `"masque les contrôles ENGO de la montre"`), toggle in **Settings / Controls** when a watch is detected, or run
  `openbridge glasses watch-controls show|hide|status`.

## Display facts measured on a real ENGO 3 (26 November 2026)

- **Orientation:** both axes are mirrored and upright text needs text rotation 4; OpenBridge does this by default
  (`--rotate on` turns the picture by 180° for an unusual mount).
- **Colours:** grey levels show yellow; the ENGO 3 has 81 red-green colours (no blue, no white), drawn with the colour
  commands and the official palette. OpenBridge uses green (ok), orange (warning), red (refused) and lime (accent).
- **Visible area:** x 0 to ~292 and y 0 to ~236 of the 304 x 256 panel on our pair (`openbridge glasses set
  --x-offset N` moves the picture if a pair differs).
- **Input:** the ENGO 3 has one input, the **double tap on the temple** (one gesture event, value 1). Single taps
  send nothing; 3-4 taps still send one event; the hand wave does nothing (ENGO 2 only). So: double tap = next (the glasses' firmware takes about 2 s to register it, and 3-4 taps still make one event — this is in the firmware, not OpenBridge; see [suggestions for ENGO](partners/engo/ENGO_FEATURE_REQUESTS.md)); on
  the home carousel the focused menu opens after 3 s; **Next / Open / Back / Home buttons** appear in the Companion
  while the glasses are connected; and "suivant", "ouvre", "retour", "accueil" said (or typed) alone on the
  Companion do the same.
- **Characters:** the fonts are ASCII only; accents are folded (`été` -> `ete`).
- **Fonts:** line heights 24 / 24 / 38 / 64 px for ids 0-3 (24 px is the smallest text); a word of n letters is
  about n x height / 2 wide. Every OpenBridge screen (home, messages, TV, volume, apps, remote, vacuum, voice,
  Oracle, sport, navigation, Ghost, intervals, settings, calibration, alerts) is laid out for these sizes inside the
  visible window: titles and list rows use the 38 px font and fall back to 24 px when the text would not fit.
- **Older ENGO demo screens** (the 38 HUD Studio features, the ENGO AI bridge) draw in top-left coordinates;
  the ActiveLook adapter converts each frame to the native frame on the way out (`to_native`), and swaps their
  colour ids for palette colours on the ENGO 3. They now show upright in the glasses and in the emulator; some of
  their long texts still run past the edge.
- **Arcs:** device angles equal logical angles (0 at 3 o'clock, clockwise as seen), start in 0-359.
- HUD Studio and the emulator draw the frames the same way (mirrored axes, text rotation, red-green palette).

What the glasses cannot do yet, and what we asked ENGO for: [suggestions for ENGO](partners/engo/ENGO_FEATURE_REQUESTS.md).

## Sport

Home → **Sport** opens running, cycling, navigation, Ghost and intervals. The dashboard shows pace or speed, distance,
time, heart rate with its zone, cadence and power when a sensor sends them. Standard Bluetooth sensors are decoded
(heart rate, running speed and cadence, cycling speed and cadence, power, smart trainers, battery). A value that has
gone stale is no longer shown as current.

- **Navigation:** load a GPX track or route. The glasses show the next turn with an arrow and its distance (announced
  at 200 m and 50 m), the distance left, an off-route warning (over 40 m off, cleared under 25 m) and the arrival.
- **Ghost:** race a previous session; the screen shows how many seconds and metres ahead or behind you are, and the
  projected finish time.
- **Intervals:** `6x400@4:15` means 10 min warm-up, 6 × 400 m at 4:15 /km with 90 s recoveries, 10 min cool-down; the glasses show the step, the target and
  what is left, and announce each change.
- Laps are taken automatically every kilometre.

```
openbridge glasses run --link studio --sport run --gpx parcours.gpx --max-hr 190
openbridge glasses run --link studio --sport run --workout 6x400@4:15
openbridge glasses run --link studio --sport run --gpx parcours.gpx --simulate 3.2   # SIMULATED walk along the track
```

`--simulate` moves a fake position along the track at the given speed (m/s), to try navigation at home; everything
it produces is marked as simulated. On a real outing the phone's GPS will feed the position; that Companion part is
next.

## Language

**Settings → Language** on the glasses switches Français / English. From the PC:

```
openbridge glasses set --lang fr            # auto | fr | en (auto follows the system, English otherwise)
openbridge glasses set --hud-lang en        # follow | fr | en: glasses in another language than the app
openbridge glasses set --units imperial     # metric | imperial, independent of the language
```

The Companion app has the same choice (the language button, first in its system buttons: Auto → Français →
English). Distances, times and paces follow the language (`1,2 km` / `1.2 km`). The PC web interface is still in
English.

## Moving around

On the ENGO 1 / 2, the gesture sensor (a hand wave in front of the right lens) drives everything:

| Gesture | Action |
|---|---|
| 1 wave | next item |
| 2 quick waves | open / press |
| 3 quick waves | back |

On the ENGO 3, a double tap on the temple is the only input: double tap = next, the home carousel opens the focused
menu after 3 s, and open / back / home come from the Companion buttons or the voice. The bottom hint of each screen
says which applies (`tap next, say open` on the ENGO 3).

The same menus answer to `openbridge glasses press next|prev|ok|back|home|up|down|left|right`, to the HUD Studio
`G` key, and to voice. A new message slides in at the top for six seconds; two waves open it.

## Safety

- **Nothing acts until you grant it, once, on the PC**, listing exactly what the glasses may do:
  `openbridge glasses grant --allow tv_remote,tv_apps,tv_power,vacuum --consent ALLOW`
  (`openbridge glasses revoke` takes it back). The grant plus one deliberate gesture or voice command counts as consent
  for one action, like the watch remote controls.
- Every action is a typed OpenBridge primitive (`device_action` key / launch_app, `tv_sleep` / `tv_wake`,
  `tuya_command`) run by the executor, with its receipt. Only the keys, apps and vacuum commands listed above are
  reachable; typing text, unlocking, garage doors and alarms are not.
- Reads (TV volume, app on screen) change nothing.

## Commands

```
openbridge glasses preview --out captures/glasses        # every screen as PNG + a contact sheet, no glasses needed
openbridge glasses grant --allow tv_remote,tv_apps,vacuum --consent ALLOW
openbridge glasses run --link studio                     # HUD Studio (python -m src.adapters.hud_studio --model "ENGO 3")
openbridge glasses run --link ble                        # real glasses over Bluetooth from this PC
openbridge glasses run --link ble --takeover             # take the glasses over from another OpenBridge process
openbridge glasses set --privacy sender --apps discord,telegram,sms,messages
openbridge glasses set --rotate on                       # if the calibration arrow is not at the top left
openbridge glasses notify --app telegram --from "Maman" --text "Tu viens ?"
openbridge glasses say "monte le son de la télé"
openbridge glasses status
openbridge glasses watch-controls status|show|hide --page main --lang fr
```

`python dev/glasses_e2e.py --out <dir> [--tv-volume] [--voice]` drives a running hub step by step through its control
port and saves a HUD Studio screenshot after each step.

## Status (23 November 2026)

| Part | Status |
|---|---|
| Menus, messages, TV and vacuum screens, voice screen | Verified in HUD Studio, end to end through `openbridge glasses run` |
| Voice understanding (phone transcript → command model → action) | Verified: "monte / baisse le son de la télé" → volume up / down; "commande une pizza" refused |
| TV actions | Reached the gate; not run on the TV (no ADB link at test time) |
| Vacuum actions | Wired through the gate; not run (no physical test requested) |
| Companion notification access + `get_notifications` | Built (APK compiles); to test on the phone |
| Sport, intervals, Ghost, GPX navigation | Engines and screens tested on simulated data and in HUD Studio |
| Bluetooth sensors (heart rate, RSC, CSC, power, trainer) | Decoders tested on the standard byte layouts; no real sensor connected yet |
| Bluetooth transport (MTU, flow control, one controller, reconnect) | Unit-tested; to measure on the real pair |
| Français / English (glasses and Companion) | Built and tested; Companion switch to try on the phone |
| Real ENGO 3 Photochromic through the phone's Bluetooth (26 Nov 2026) | Verified by the owner wearing them: menus upright and readable, colours from the palette, Oracle answer to a question spoken into the phone shown on the glasses |
| Real ENGO 3 Photochromic over Bluetooth from the PC | Not tested (this PC has no Bluetooth). Previously: waiting for the glasses. First: the **calibration screen** (Settings → Calibrate display) to check orientation, then colours and fonts. Procedure: [validation report](partners/engo/22_REAL_HARDWARE_VALIDATION_REPORT.md) |

Known gaps: on the move (no PC nearby) the glasses need the phone to hold the Bluetooth link itself and to feed its
GPS; that Companion part is the next step.

Every feature, its status and its evidence: [traceability matrix](partners/engo/21_FEATURE_TRACEABILITY_MATRIX.md).
The contracts behind it: [API and data contracts](partners/engo/24_API_AND_DATA_CONTRACTS.md).
