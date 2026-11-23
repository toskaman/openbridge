# API and SDK audit

An integrator's report on your device's API or SDK, written by someone who just integrated it: what works, what
surprises, what the documentation does not say, and how to reproduce each finding.

## What it covers

- **Protocol and transport**: discovery, pairing, authentication, timeouts, rate limits, reconnection, local versus
  cloud paths.
- **State and read-back**: can every change be read back? How fast? Are there states the API cannot report?
- **Reversibility**: which settings can be restored exactly, which commands are irreversible.
- **Safety and privacy**: what a third-party integration can do that it should not (unlock, firmware, credentials),
  what personal data the API exposes.
- **Documentation gaps**: every place where the integrator had to guess, with the answer found.
- **Firmware pitfalls**: behaviour that changed between versions.
- **Developer experience**: time to first command, error messages, SDK quality, licence terms.

## What you receive

A written report (Markdown or PDF), one reproducible test case per finding (script, emulator or recorded trace),
a prioritised list of fixes, and an emulator of your device that your own CI can use. Confidential findings stay
under NDA and out of the public repository (see [Privacy](../PRIVACY.md#partners-and-confidential-material)).

## An example

The [ENGO / ActiveLook dossier](ENGO.md) (19 documents: hardware, BLE protocol and opcodes, HUD features, emulator,
integration plan, ergonomics benchmark) was produced this way, before the hardware arrived.

Ask for a quote: [info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20API%20audit).
