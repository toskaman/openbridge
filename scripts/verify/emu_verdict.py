"""Adaptive emulator acceptance verdict helpers (Campaign One, Frontier 90).

Verdict taxonomy (staged, mutually exclusive):
  BOOT_FAIL              emulator never reached sys.boot_completed=1
  ADB_DEAD               adb channel dead/unresponsive (incl. prior-run "error: closed")
  APP_CRASH              app has no live pid after launch
  APP_BEHAVIOR_FAIL      app alive but not foreground / version probe failed
  EVIDENCE_FAIL_AFTER_PASS  product assertions passed, evidence capture failed
  PASS                   all stages green

Prior-run evidence mapped here:
  run 41256301271 (phone) + run 41259765640 (phone/wear): emulator death and
  bare "error: closed" from adb. Those signatures classify as ADB_DEAD (adb
  channel) or BOOT_FAIL (boot_completed never 1), both retryable infra flakes.
  Product assertions (pid/foreground/version) are NEVER retried silently.

Retry policy (enforced by emu_harness.sh, mirrored here):
  BOOT retries: BOOT_RETRIES (default 2) — re-probe boot_completed only.
  ADB retries:  ADB_RETRIES (default 2)  — adb reconnect/kill-server only.
  APP_*/EVIDENCE_*: no retries.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

BOOT_FAIL = "BOOT_FAIL"
ADB_DEAD = "ADB_DEAD"
APP_CRASH = "APP_CRASH"
APP_BEHAVIOR_FAIL = "APP_BEHAVIOR_FAIL"
EVIDENCE_FAIL_AFTER_PASS = "EVIDENCE_FAIL_AFTER_PASS"
PASS = "PASS"

VERDICTS = (
    BOOT_FAIL,
    ADB_DEAD,
    APP_CRASH,
    APP_BEHAVIOR_FAIL,
    EVIDENCE_FAIL_AFTER_PASS,
    PASS,
)

# Infra-flake verdicts: the ONLY ones eligible for bounded retry.
RETRYABLE = frozenset({BOOT_FAIL, ADB_DEAD})

# Signatures observed in prior runs 41256301271 / 41259765640 + close cousins.
_ADB_DEAD_PATTERNS = (
    "error: closed",
    "error: device offline",
    "error: device not found",
    "error: no devices",
    "no devices/emulators found",
    "device offline",
    "unauthorized",
    "adb server version",
    "cannot connect to daemon",
    "connection refused",
    "no emulator instance",
    "emulator: error",
    "qemu: terminating",
    "adb_devices_failed",
)


def classify_adb_output(text: str) -> str | None:
    """Return ADB_DEAD if text carries a dead-channel signature, else None."""
    lowered = (text or "").lower()
    for pat in _ADB_DEAD_PATTERNS:
        if pat in lowered:
            return ADB_DEAD
    return None


def is_retryable(verdict: str) -> bool:
    """True only for infra flakes (boot/adb). Product verdicts never retry."""
    return verdict in RETRYABLE


def write_verdict(path_txt: str, path_json: str, verdict: str, stage: str,
                  device: str, detail: str = "", attempts: int = 1) -> dict:
    """Write staged verdict file (.txt) + machine-readable sidecar (.json)."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    record = {
        "verdict": verdict,
        "stage": stage,
        "device": device,
        "detail": detail[:2000],
        "attempts": attempts,
        "retryable": is_retryable(verdict),
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(path_txt, "w", encoding="utf-8") as fh:
        fh.write(f"VERDICT={verdict}\n")
        fh.write(f"STAGE={stage}\n")
        fh.write(f"DEVICE={device}\n")
        fh.write(f"ATTEMPTS={attempts}\n")
        fh.write(f"DETAIL={detail[:500]}\n")
    with open(path_json, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    return record


if __name__ == "__main__":  # CLI: emu_verdict.py <txt> <json> <verdict> <stage> <device> [detail] [attempts]
    import sys

    args = sys.argv[1:]
    if len(args) < 5:
        raise SystemExit("usage: emu_verdict.py <txt> <json> <verdict> <stage> <device> [detail] [attempts]")
    txt, js, verdict, stage, device = args[:5]
    detail = args[5] if len(args) > 5 else ""
    attempts = int(args[6]) if len(args) > 6 else 1
    rec = write_verdict(txt, js, verdict, stage, device, detail, attempts)
    print(f"VERDICT={rec['verdict']} STAGE={stage} DEVICE={device}")
