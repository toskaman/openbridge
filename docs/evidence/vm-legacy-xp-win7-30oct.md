# Legacy Windows agents: XP SP3 + Win7 SP1 QEMU proofs (30 Oct 2026)

Ship test of the BridgeWindows-v4 legacy x86 agent (`agents/agent-win-x86-legacy.exe`,
SHA256 `4b841f19ef888ec5a52b95badfc41246f6129641d600d1a0cff6fea586051eee`,
204800 bytes, PE32 i386, subsystem 5.01, MSVCRT-linked, embedded software
SHA-256/HMAC, no Vista+ imports) against two real guest installs on E:.

## Windows XP Professional SP3 x86 (QEMU, WHPX, qemu32 CPU)

- Install: `winxp-pro-sp3-vl-x86.iso`, winnt.sif-unattended, agent copied from
  floppy, provision `host=10.0.2.2 port=9876 agent-id=winxp-vm-01`.
- Daemon `/status`: `winxp-vm-01 127.0.0.1 windows x86 v4.0.0` connected.
- Guest agent console shows `[CONNECTED] Connected to Master at 10.0.2.2:9876`.
- RPC round-trip via `bridge_cli.py --agent winxp-vm-01 exec`:

```text
OB-XP-VIDEO-PROOF
winxp-vm
Microsoft Windows XP [Version 5.1.2600]
```

exit 0. Screenshot: `docs/jury/screens/legacy-xp-agent-connected.png`
(agent window with EXEC SUCCESS), `legacy-xp-desktop-taskbar.png` (desktop).

## Windows 7 Professional SP1 x86 (QEMU, WHPX, qemu32 CPU)

- Install: `win7-pro-sp1-x86.iso`, minimal autounattend.xml (windowsPE +
  specialize only; oobeSystem stripped after repeated `0x8030000b`), manual
  OOBE click-through (user `ob`, no password, updates "Ask me later",
  Work network), agent copied from A:, provision `agent-id=win7x86-vm-01`.
- UAC elevation prompt accepted on-screen (screenshot
  `legacy-win7-uac-consent.png`): admin consent is explicit, never bypassed.
- Daemon `/status`: `win7x86-vm-01 127.0.0.1 windows x86 v4.0.0` connected
  (3 agents total: PC2 x64 + XP x86 + Win7 x86).
- Guest agent GUI shows CONNECTED + LINKED to 10.0.2.2:9876 with orb
  (screenshot `legacy-win7-agent-connected.png`).
- RPC round-trip via `bridge_cli.py --agent win7x86-vm-01 exec`:

```text
OB-WIN7-PROOF
WIN7X86-VM
Microsoft Windows [Version 6.1.7601]
```

exit 0.

## Scope notes

- Full guest OS, NAT networking, real mutual-auth handshake (v4 wire protocol).
- Test installs only (XP VLK from owner-provided gist, Win7 generic KMS key in
  grace period); VMs deleted after proofs per owner order, trace kept here.
- Legacy crypto is in-process software SHA-256/HMAC validated against
  `hashlib` + RFC 4231 vectors on host and guest (`test_legacy_agent.py` 3/3).
