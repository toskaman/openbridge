# ESP32 agent: native IDF app on Espressif QEMU proof (30 Oct 2026)

Ship test of the BridgeWindows-v4 ESP32 agent (`agents/esp32-ob/`, BridgeWindows
`625d7e7`): a native ESP-IDF v5.4 app sharing the dependency-free v4 protocol
core (`proto/obproto.cpp` + `proto/sha256.cpp`, byte-identical logic to the
Arduino build and the host test) against Espressif QEMU (`esp32` machine) on E:.

QEMU has no WiFi radio, so the emulated link runs over UART0 through the host
serial gateway (`agents/esp32-ob/serial_gateway.py`): the firmware emits one
`OB-SER-SYNC` marker line, then pure v4 bytes; the gateway drops everything
before the marker (ROM/bootloader chatter) and pipes the rest to the master
over TCP. Authentication and MACs terminate at the bridge, never in the gateway.

## Build

- IDF app (`agents/esp32-ob/idf/`, target esp32, DIO flash 40 MHz, quiet boot):
  `idf.py set-target esp32 && idf.py build`, image merged with `esptool
  merge_bin` (bootloader + partition table + app) and padded to 2 MB for QEMU.
- Host protocol proof (same core on host TCP): `test_esp32_proto.py` 3/3
  (selftest vectors, handshake/ping/diag, exec allowlist + MAC tamper).
- Gateway proof: `test_serial_gateway.py` 3/3 (marker sync incl. split chunks
  and `\r\n` line ends, untouched bidirectional pipe, `--serial-port` contract).

## Live proof 1: link + RPCs (log `E:/VMs/logs/esp32-qemu-proof.log`)

- QEMU: `-machine esp32 -drive file=<2 MB image>,if=mtd,format=raw -serial
  tcp:127.0.0.1:5599,server -display none -no-reboot`.
- Gateway: `SYNC after 382 dropped bytes` (ROM chatter), then pure v4.
- Bridge: `Agent 'ESP32-01' authenticated` (mutual HMAC over emulated UART).
- `sys.ping` → `pong`, `uptime_ms` from firmware.
- `exec.run screen.text HelloESP32QEMU` → exit 0.
- `exec.run led on` → exit 0.

## Live proof 2: cross-device flow (log `E:/VMs/logs/esp32-qemu-proof2.log`)

Two agents on one bridge: `ESP32-01` (QEMU UART) + `HOST-2` (host harness).

```text
BOTH_AUTHED: True ['ESP32-01', 'HOST-2']
ESP32_LED: exit_code 0 (stdout 'led on')
HOST_FWD: exit_code 0 (stdout 'screen.text ESP32-LED-ON')
CROSS_OK: True
```

The ESP32 outcome drives a command to the other agent through the master.
Screenshot: `docs/jury/screens/esp32-idf-qemu-proof.png` (proof transcript).

## Why IDF, not Arduino, in emulation

The Arduino build boots and self-tests on QEMU (SHA256/HMAC/FRAMING vectors
OK over serial) but then dies: WiFi `WiFi.begin()` asserts (no radio/PHY in
QEMU), and serial-mode builds panic non-deterministically in framework code
(`initArduino` OTA-partition mmap at boot; later FreeRTOS `waiti`/IPC cache
faults decoded via addr2line). A dozen firmware iterations confirmed the Arduino +
QEMU-ESP32 cache model is unstable here, so the emulated target is the IDF app
(QEMU-ESP32's officially supported target). The Arduino sketch keeps the
physical path below, including its serial/USB mode.

## Physical deployment recipe (pending hardware; no ESP32 in lab)

- Same IDF app: `idf.py -p COMx flash monitor` on any ESP32-DevKit, then
  `serial_gateway.py --serial-port COMx - <bridge-host:port>` (needs
  `pip install pyserial`).
- Or the Arduino WiFi build: open `agents/esp32-ob/ob_esp32/ob_esp32.ino` in
  Arduino IDE / arduino-cli (`esp32:esp32:esp32`), set WiFi + master + PSK,
  upload; wire ILI9341 TFT_CS=5 TFT_DC=27 TFT_RST=4 MOSI=23 SCK=18 MISO=19.

## Scope notes

- Emulated UART link only; WiFi association is unproven anywhere (no radio in
  QEMU, no hardware in lab) and stays out of the registry row.
- TFT UI code ships in the Arduino physical build; no pixels exist in emulation.
- Loopback PSK is the firmware default and was used for the proof bridges only
  (torn down after); production bridges must use a long random PSK.
- v4 frames are authenticated (mutual HMAC), NOT encrypted: trusted LAN only.
