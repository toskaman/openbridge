# Security policy

OpenBridge acts on real devices in real homes and companies, so security reports get top priority.

## Reporting a vulnerability

**Please do not open a public issue or discussion for a security problem.**

Email **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=%5BSECURITY%5D%20OpenBridge)** with the subject line
`[SECURITY] OpenBridge`, and include:

- what you found and where (file, endpoint, protocol message or device flow);
- the steps to reproduce it, and the version or commit you tested;
- the impact you expect (for example: an action executed without consent, a pairing bypass, data leaving the machine);
- whether you would like to be credited, and under which name.

What happens next:

1. You get an acknowledgement, normally within **3 working days**.
2. The report is reproduced and assessed, and you are kept informed of progress.
3. A fix is prepared privately, tested, and released. Advisories are published once users can update.
4. With your permission, you are credited in the advisory and the [changelog](CHANGELOG.md).

Reports in English or French are both welcome. Good-faith research that respects the rules below will not be
pursued.

## Scope

In scope: everything in this repository, including the PC server, the CLI, the local web interface, the relay and
pairing protocol, the Android / Android TV / Wear OS companion, the device adapters, the PC agents and the
ENGO / ActiveLook bridge.

Out of scope: third-party products and services that OpenBridge talks to (report those to their vendors; if the
issue affects OpenBridge users, a short note to us helps too), and denial of service by flooding a device on your
own network.

## Rules for testing

- Test only on devices and accounts you own, or have written permission to test.
- Do not access, change or delete other people's data.
- Give us reasonable time to ship a fix before any public disclosure.

## Automated checks

- **CodeQL** analyses the Python server, the web interface and the Android companion on every change and weekly.
- **OpenSSF Scorecard** publishes an independent score of the project's security practices.
- **Signed commits and tags** from the maintainer.
- **The Windows download** is built in CI, smoke-tested, and published with Sigstore build provenance. Check a download
  with `gh attestation verify OpenBridge-Windows-x64.zip --repo toskaman/openbridge`.

## Supported versions

Security fixes land on the `main` branch first, then in a patch release of the supported versions listed in the
[support policy](docs/SUPPORT.md) (today: 0.5.x; critical fixes for 0.4.x until 23 February 2027). Each release
download comes with a Sigstore build attestation and a CycloneDX SBOM (`OpenBridge-Windows-x64.cdx.json`, also
attested).

## Security design, in short

- **Consent first:** privileged actions need the owner's explicit approval, and every grant can be revoked.
- **Verified outcomes:** the device is read back after each action; unconfirmed results are labelled *unverified*.
- **Signed relay messages:** pairing uses an on-device code; messages are sealed (AEAD), expire, and are protected
  against replay.
- **Local by default:** the AI runs on the owner's machine and nothing is sent to a cloud unless the owner connects
  a remote AI by hand. See the [privacy note](docs/PRIVACY.md).

Details: [relay security](docs/RELAY_SECURITY.md) · [transactions and undo](docs/TRANSACTION_AND_UNDO.md) ·
[known limitations](docs/KNOWN_LIMITATIONS.md).
