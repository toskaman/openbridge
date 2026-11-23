<p align="center">
  <a href="https://www.engoeyewear.com"><img src="../assets/readme/partner-engo.svg" width="100%" alt="Official hardware partner: ENGO smart glasses, powered by ActiveLook by Microoled"></a>
</p>

# ENGO × OpenBridge

**Your devices, in your field of view.**

[ENGO](https://www.engoeyewear.com) designs heads-up display (HUD) smart glasses in Grenoble, France. They are built on [ActiveLook](https://www.activelook.net), Microoled's ultra-light, low-power micro-OLED display platform, driven over Bluetooth Low Energy.

ENGO is OpenBridge's first official hardware partner and is sending a pair of smart glasses for integration and testing (covering the ENGO 2 and newly launched ENGO 3 generation).

## Supported Hardware Generations

| Model | Weight | Optics & Display | Battery | Connectivity | Special Features |
|---|---|---|---|---|---|
| **ENGO 1** (2021) | ~42g | MicroOLED (Monochrome Yellow) | 10–12h | BLE 4.2 | Proximity gesture sensor |
| **ENGO 2** (2022+) | 36g (Std) / 41g (Lrg) | MicroOLED (Monochrome Yellow, 10k nits) | 10–12h | BLE 5.0 | Magnetic pogo-pin dock, IP54 |
| **ENGO 3** (Current) | **38.5g** (Std) / **41g** (Cyclist) | **MultiColor MicroOLED** (Green/Amber/Red zones) | **18–20h** | **Bluetooth 5.4** | Color zone alerts, IP55, engo Compagnon app |
| **ENGO 3 Titanium** | **28.9g** (3D printed) | **MultiColor MicroOLED** | **24h+** | **Bluetooth 5.4** | Aerospace-grade 3D-printed titanium frame |

## Why a heads-up display

OpenBridge already lets you ask any screen (TV, watch, phone, PC) to control the devices around you. Glasses add something no other screen can: **information that reaches you without you looking for it.**

| Situation | Without glasses | With ENGO + OpenBridge |
|---|---|---|
| You send the vacuum back to its dock | Walk over or open an app to check | “Vacuum · docking” appears, then “Docked ✓” |
| An action is refused for safety | You find out later, in the activity log | The reason shows up in your view right away |
| You're wiring a test bench | Look away to a screen for every reading | Sensor values and alerts stay in sight |
| A device drops off the network | Nothing, until something fails | A short alert, the moment it happens |

## What we're building

1. **ActiveLook adapter.** Discover and pair the glasses like any other OpenBridge device, with a verified evidence record.
2. **Status layouts.** A compact, glanceable view of the devices you care about.
3. **Alerts and confirmations.** Refusals, offline devices and “Done, verified” receipts pushed to the display.
4. **Display only, by design.** The glasses show information; they never trigger privileged actions on their own. Every action still goes through approval and read-back.

👉 **Open the dedicated technical dossier: [ENGO × OpenBridge R&D Hub](engo/README.md)**  
*(Detailed hardware specifications, BLE protocol manual, emulator guide, catalogue of 10+ features and integration architecture)*

## Progress

- [x] Partnership confirmed with ENGO
- [ ] Hardware received
- [ ] BLE connection and evidence record (real hardware)
- [ ] Status layout on the glasses
- [ ] Alerts and confirmations
- [ ] Filmed demo with TV, watch and robot vacuum
- [ ] Public, verified compatibility report

Every step will be logged in the [evidence registry](../DEVICE_EVIDENCE.json) once it runs on the real glasses, with the same rules as the rest of the project: nothing simulated is ever counted as physical proof.

## Links

- ENGO glasses: [engoeyewear.com](https://www.engoeyewear.com)
- ActiveLook platform: [activelook.net](https://www.activelook.net)
- Partner program: [what a partnership brings](README.md)
- OpenBridge: [back to the project](../../README.md)

<sub>ENGO, ActiveLook and Microoled names and logos are trademarks of their respective owners and are shown here as part of the hardware partnership.</sub>
