# P30 CLI orchestration phone+AVD (30 Oct 2026)

Multi-device workflow executed entirely through the CLI with preview-bound
consent: wf-p30-phone-avd2, status done, 3/3 EXECUTED.

- cap-phone: BV9300 Pro USB, 2388x1080 frame stored (1,791,400 bytes).
- cap-avd: sdk_gphone64_x86_64 emulator-5556, 1080x2400 frame stored.
- montage: 4776x2400 montage of 2 on fabric (5,159,134 bytes).
- Independent check: sha256 of the stored montage recomputed locally,
  match True (d4b019c08965c603...).
- Screenshot: E:/shots/p30_phone_avd_montage.png (+ manifest line).
- Fault run wf-p30-fault: offline ghost FAILED honestly, phone EXECUTED,
  re-run refused ALREADY_RECORDED (no blind replay).
- Labels, not keys, address targets (keys rotate per boot; CLI resolves).
