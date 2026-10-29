# VM fleet proof (29 Oct 2026)

Goal: prove the OpenBridge agent runs beyond the two dev PCs. All VM disk on
`E:\VMs` (never C:). Host: Windows 10, QEMU 11.1.0 WHPX-accelerated.

## Proven (handshake logs, mutual PSK + ping/diag/exec)

| VM | OS | Kernel / Python | SSH | Proof |
|---|---|---|---|---|
| deb1 | Debian 13 trixie | 6.12.107 / 3.13.5 | 127.0.0.1:2222 | `E:/VMs/logs/agent-handshake-deb1-FINAL.log` (id=DEB1) |
| deb2 | Debian 13 trixie | 6.12.107 / 3.13.5 | 127.0.0.1:2223 | `E:/VMs/logs/agent-handshake-deb2.log` (id=DEB2) |
| deb12 | Debian 12 bookworm | 6.1.0-50 / 3.11.2 | 127.0.0.1:2224 | `E:/VMs/logs/agent-handshake-deb12.log` (id=DEB12) |
| ub22 | Ubuntu 22.04.5 server | 6.8.0-138 / 3.10.12 | 127.0.0.1:2225 | `E:/VMs/logs/agent-handshake-ub22.log` (id=UB22) |
| arm64 | Debian 13 trixie aarch64 | 6.12.107 / 3.13.5 | 127.0.0.1:2226 | `E:/VMs/logs/agent-handshake-arm64.log` (id=ARM64) |

Method: preseed (Debian) / nocloud-net autoinstall (Ubuntu) over QEMU
user-net (`http://10.0.2.2:8000`, host file server), SSH key `E:/VMs/keys/ob_vm`,
`agent_reference.py` (fixed nested-nonce handshake, BridgeWindows-v4 7b32f88)
against `E:/VMs/tools/minibridge.py` (nested dialect, ports 19876+).

Install serial logs: `E:/VMs/logs/deb1-install-serial.log`,
`deb2-install-serial.log`, `deb12-install-serial.log`, `ub22-install-serial.log`.

## Ubuntu notes (real obstacles, solved)

- `releases.ubuntu.com` 403 was file-specific (24.04.3 desktop); 22.04.5 server
  ISO downloaded from `ubuntu.mirrors.ovh.net`, size 2136926208 bytes,
  sha256 `9bc60288…aa98b0` verified against upstream SHA256SUMS.
- 22.04 has no legacy d-i netboot (404) → used the server ISO kernel+initrd
  (extracted with a 60-line stdlib ISO9660 reader, `isoread.py`) plus
  nocloud-net autoinstall over HTTP. No seed ISO tool needed.
- The 22.04.5 ISO ships no GA `vmlinuz` (grub default entry is dangling);
  used the HWE pair (`hwe-vmlinuz` + `hwe-initrd`).
- First install had no network: hardcoded `eth0` vs predictable `enp0s3`.
  Fix: no `network:` section (keep installer DHCP). Reinstalled.

## Honest blockers (not attempted, no fake claims)

- **Windows XP**: ISO present (`winxp_sp3_x86.iso`, 589 MB) but unattended setup
  requires a product key and no license is available. Not installed.
  Additionally `agent.c` targets `_WIN32_WINNT 0x0601` (Win7+): an XP agent
  would need an XP-targeted rebuild (BCrypt/GetTickCount64 unavailable on XP).
- **Windows 7**: no ISO anywhere on E: (full-disk hunt). Nothing staged.
  Win7 setup allows keyless install (30-day grace), so this is media-only.
- **ARM64: PROVEN.** `debian-installer/arm64/linux+initrd.gz` (trixie), direct
  kernel boot on `-machine virt` (TCG, ~1 h install):
  `E:/VMs/logs/arm64-install-serial.log` ends with `Finishing the installation`
  + `reboot: Restarting system`. The UEFI disk boot had no GRUB (installed
  without UEFI present), so the kernel+initrd were extracted from the installed
  disk with a stdlib GPT+ext4 reader (`ext4get.py`) and the disk is booted
  direct-kernel (`root=/dev/vda3 console=ttyAMA0`):
  `E:/VMs/logs/arm64-boot-serial.log` shows the `ob-arm64 login:` prompt with
  sshd up. Agent handshake: `E:/VMs/logs/agent-handshake-arm64.log`
  (`arch=aarch64`, mutual PSK, ping/diag/exec OK).
- **x86 (32-bit) guest**: no i386 media staged.

## Incidental finding (fixed same day)

`agents/agent_reference.py` read `auth.challenge.master_nonce` top-level while
both bridges (`bridge_mcp.py`, `windows_bridge.py`) send it nested in
`params` (C agents match via whole-document key search, so only the reference
agent was broken). Live-verified RED (`FAIL reference agent connects`), fixed
with nested-first + top-level fallback, GREEN 8/8. Doc:
`docs/AGENT_PROTOCOL.md` in BridgeWindows-v4.
