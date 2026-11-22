# Privacy note

**Short version: by default, nothing leaves your network.** OpenBridge runs on your own machine, talks to your
devices over your local network, USB or Bluetooth, and keeps its records on your disk.

## What stays local

| Data | Where it lives |
|---|---|
| Your requests (typed or spoken) | Processed on your PC by the local AI models. Voice clips are transcribed on the PC. |
| The device inventory (what was discovered and what each device can do) | Stored on your PC. |
| Receipts, approvals and evidence logs | Stored on your PC, in the OpenBridge data folder. |
| Pairing keys for the phone, TV and watch companions | On your PC and on the paired device. Revoking a pairing removes the key. |

OpenBridge contains **no telemetry, no analytics and no crash reporting**. It does not phone home.

## When something does leave your machine

Only in these cases, and only because you asked for it:

- **You connect a remote AI or API by hand** (for example OpenRouter, or a model server on another computer).
  Your request is then sent to the address you declared, and only to that address. OpenBridge asks for your
  consent for each request sent to an AI that is not on this PC. See [Connect your own AI](AI_PROVIDERS.md).
- **You download models or updates** yourself, from the source you choose.
- **A device you control talks to its own vendor's cloud.** That is between the device and its maker;
  OpenBridge prefers local protocols whenever the device offers them.

## Partners and confidential material

When a partner shares documentation, SDKs, firmware or test data under NDA, it stays **out of the public
repository**. Only what the partner approves is published: adapter code, test results and the compatibility
report. Partner data is never used for anything other than the integration it was shared for.

## Questions

Write to **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Privacy)**. Security problems
follow the [security policy](../SECURITY.md).
