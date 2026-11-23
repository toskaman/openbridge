# Verified by OpenBridge

![Verified by OpenBridge, example](../assets/badges/verified-tv-companion-01.svg)

A label a device **earns from public evidence**. It is never sold, never granted by hand, and it lapses: a partner
plan pays for the integration and test work that produces the evidence, not for the label.

## The rule

`python scripts/verify/verified_label.py` reads [DEVICE_EVIDENCE.json](../DEVICE_EVIDENCE.json) and grants the label
to a device when:

1. at least **3 runs** are recorded with status `VERIFIED` on **real hardware** (emulators and virtual machines never
   count),
2. on at least **2 different days**,
3. covering at least **5 distinct operations**,
4. each run names an **independent oracle** (how the result was checked without trusting OpenBridge: a screen dump,
   a vendor app, a power meter, a second device) and its **evidence files exist** in the repository or at a public URL,
5. the latest run is **less than 180 days old**. A new run renews the label; a device nobody re-tests loses it.

A reviewer also checks, on the same runs, what a script cannot judge alone: that refusals happen before anything is
sent, that Undo restores the exact previous state, that a device that ignores a command is never reported done, and
that the limitations are written down. A failure is recorded as such; it is never edited away.

## Today

| Device | Status |
|---|---|
| Android TV with the companion app (`tv-companion-01`) | ![](../assets/badges/verified-tv-companion-01.svg) |
| Android phone with the companion app (`phone-companion-01`) | ![](../assets/badges/verified-phone-companion-01.svg) |
| Galaxy Watch (`watch-sm-l310-01`) | ![](../assets/badges/verified-watch-sm-l310-01.svg) |
| Tuya robot vacuum (`vacuum-tuya-01`) | ![](../assets/badges/verified-vacuum-tuya-01.svg) (2 of 3 runs) |

Badges are regenerated with `--device ID --badge FILE`; the script's output is the authority, not the picture.

## Using the label

A partner whose device holds the label may show the badge on its product page and packaging **with the date**
("Verified by OpenBridge, until 2027-04-30") and a link to the device's evidence. The label says: *this device, with
this integration, did what was recorded, checked independently*. It says nothing about safety certification,
regulatory compliance or other firmware versions. "OpenBridge" is also a trademark of other companies in other fields;
the label is used only as "Verified by OpenBridge" together with the link.
