#!/usr/bin/env bash
# Adaptive emulator acceptance harness — Campaign One §3.2 (Frontier 90).
#
# Staged verdicts: BOOT_FAIL / ADB_DEAD / APP_CRASH / APP_BEHAVIOR_FAIL /
#                  EVIDENCE_FAIL_AFTER_PASS / PASS  (see emu_verdict.py)
#
# Retry isolation (hard rule):
#   - BOOT stage:  up to BOOT_RETRIES re-probes of sys.boot_completed only.
#   - ADB stage:   up to ADB_RETRIES adb reconnect/kill-server cycles only.
#   - APP/evidence stages: NO retries — product assertions run exactly once.
#     A product failure is final; the harness never re-runs it silently.
#
# Prior-run mapping (runs 41256301271 phone, 41259765640 phone/wear):
#   "error: closed" / emulator death -> ADB_DEAD (retryable) or BOOT_FAIL
#   (retryable). Anything after successful launch is APP_* (final).
#
# Env: EMU_DEVICE (phone|wear, required), EMU_APK (path, required),
#      EMU_PKG (default fr.openbridge.companion),
#      EMU_ACTIVITY (default .MainActivity),
#      BOOT_RETRIES (default 2), ADB_RETRIES (default 2),
#      no screencap on phone (pid/foreground probes); wear uses screencap.
#
# Outputs (always preserved, success or failure):
#   <device>-verdict.txt, <device>-verdict.json, <device>-diag.txt,
#   <device>-logcat.txt (+ pid/foreground/version or launch.png per device).
set -u
DEVICE="${EMU_DEVICE:?set EMU_DEVICE=phone|wear}"
APK="${EMU_APK:?set EMU_APK=path/to/apk}"
PKG="${EMU_PKG:-fr.openbridge.companion}"
ACTIVITY="${EMU_ACTIVITY:-.MainActivity}"
BOOT_RETRIES="${BOOT_RETRIES:-2}"
ADB_RETRIES="${ADB_RETRIES:-2}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { echo "[emu-harness:$DEVICE] $*"; }
verdict() { # verdict <VERDICT> <stage> <detail> <attempts> ; exits 0 on PASS else 1
  python3 "$HERE/emu_verdict.py" "$DEVICE-verdict.txt" "$DEVICE-verdict.json" \
    "$1" "$2" "$DEVICE" "$3" "$4"
  [ "$1" = "PASS" ]
}

dump_diag() { # dump_diag <context> — always preserved, never fails the harness
  say "collecting diag artifacts ($1)"
  {
    echo "--- context: $1 ---"
    echo "--- adb devices ---"
    adb devices -l 2>&1 || echo "ADB_DEVICES_FAILED"
    echo "--- sys.boot_completed ---"
    adb shell getprop sys.boot_completed 2>&1 || echo "GETPROP_FAILED"
    echo "--- pid ---"
    adb shell pidof "$PKG" 2>&1 || echo "NO_PID"
    echo "--- foreground probe ---"
    cat "$DEVICE-foreground.txt" 2>/dev/null || echo "NO_FOREGROUND_FILE"
  } | tee "$DEVICE-diag.txt" 2>/dev/null || true
  adb logcat -d > "$DEVICE-logcat.txt" 2>/dev/null || true
  adb shell dumpsys activity activities > "$DEVICE-activities.txt" 2>/dev/null || true
  timeout 120 adb bugreport "$DEVICE-bugreport.zip" 2>/dev/null \
    || echo "BUGREPORT_FAILED" > "$DEVICE-bugreport-failed.txt"
  ls -la "$DEVICE"-* 2>/dev/null || true
}

adb_dead_probe() { # returns 0 if adb channel looks dead; prints signature
  local out
  out="$(adb devices 2>&1)" || { echo "adb devices exit=$? $out"; return 0; }
  if echo "$out" | grep -qiE "error: closed|offline|unauthorized|no devices|not found"; then
    echo "$out" | head -3
    return 0
  fi
  if ! echo "$out" | grep -q "device$"; then
    echo "no attached device: $out" | head -3
    return 0
  fi
  return 1
}

# ---------- STAGE 0: BOOT (retryable: re-probe only) ----------
say "stage=boot (retries=$BOOT_RETRIES)"
boot_attempt=0
boot_ok=0
while [ "$boot_attempt" -le "$BOOT_RETRIES" ]; do
  boot_attempt=$((boot_attempt + 1))
  if timeout 120 adb wait-for-device 2>/dev/null \
     && adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
    boot_ok=1
    break
  fi
  say "boot probe attempt $boot_attempt/$((BOOT_RETRIES + 1)) failed"
  sleep 10
done
if [ "$boot_ok" != 1 ]; then
  dump_diag "boot"
  verdict BOOT_FAIL boot "sys.boot_completed!=1 after $boot_attempt attempts" "$boot_attempt"
  exit 1
fi

# ---------- STAGE 1: ADB health (retryable: reconnect only) ----------
say "stage=adb (retries=$ADB_RETRIES)"
adb_attempt=0
adb_ok=0
adb_sig=""
while [ "$adb_attempt" -le "$ADB_RETRIES" ]; do
  adb_attempt=$((adb_attempt + 1))
  if adb_sig="$(adb_dead_probe)"; then
    say "adb probe attempt $adb_attempt/$((ADB_RETRIES + 1)) dead: $adb_sig"
    adb reconnect 2>/dev/null || adb kill-server 2>/dev/null || true
    sleep 10
    timeout 60 adb wait-for-device 2>/dev/null || true
  else
    adb_ok=1
    break
  fi
done
if [ "$adb_ok" != 1 ]; then
  dump_diag "adb"
  verdict ADB_DEAD adb "adb channel dead after $adb_attempt attempts: $adb_sig" "$adb_attempt"
  exit 1
fi

# ---------- STAGE 2: PRODUCT ASSERTIONS (single pass, NO retries) ----------
say "stage=app (single pass, no retries)"
# From here on, any failure is final — the harness exits without re-running.
if ! adb install --no-incremental "$APK" 2>&1 | tee "$DEVICE-install.txt"; then
  dump_diag "install"
  verdict APP_CRASH install "adb install failed (single attempt, no retry)" 1
  exit 1
fi
adb shell pm grant "$PKG" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
adb shell pm grant "$PKG" android.permission.RECORD_AUDIO 2>/dev/null || true
adb shell am start -n "$PKG/$ACTIVITY" 2>&1 | tee "$DEVICE-start.txt" || true

ok=0
for i in 1 2 3 4 5 6; do
  sleep 5
  # NOTE: bounded settle polling, NOT retries — one assertion window, one verdict.
  adb shell pidof "$PKG" 2>/dev/null | tee "$DEVICE-pid.txt" || true
  adb shell dumpsys activity activities 2>/dev/null \
    | grep -m1 -i openbridge | tee "$DEVICE-foreground.txt" || true
  if [ -s "$DEVICE-pid.txt" ] && [ -s "$DEVICE-foreground.txt" ]; then ok=1; break; fi
  say "settle poll $i/6: pid/foreground not ready"
done
if [ ! -s "$DEVICE-pid.txt" ]; then
  dump_diag "app-no-pid"
  verdict APP_CRASH app "no live pid after launch (single pass, no retry)" 1
  exit 1
fi
if [ "$ok" != 1 ]; then
  dump_diag "app-not-foreground"
  verdict APP_BEHAVIOR_FAIL app "pid alive but not foreground after settle window (no retry)" 1
  exit 1
fi

# ---------- STAGE 3: EVIDENCE (no retry; failure after pass is its own verdict) ----------
say "stage=evidence"
evidence_fail=""
adb shell dumpsys package "$PKG" 2>/dev/null | grep -m1 versionName \
  | tee "$DEVICE-version.txt" || evidence_fail="version probe failed"
if [ "$DEVICE" = "wear" ]; then
  adb exec-out screencap -p > wear-launch.png 2>/dev/null \
    || evidence_fail="${evidence_fail}; wear screencap failed"
fi
adb logcat -d -t 300 > "$DEVICE-logcat.txt" 2>/dev/null \
  || evidence_fail="${evidence_fail}; logcat capture failed"
if [ ! -s "$DEVICE-logcat.txt" ]; then
  evidence_fail="${evidence_fail}; logcat empty"
fi
if [ -n "$evidence_fail" ]; then
  dump_diag "evidence"
  verdict EVIDENCE_FAIL_AFTER_PASS evidence "product PASS, evidence failed: $evidence_fail" 1
  exit 1
fi

dump_diag "pass"
verdict PASS done "all stages green" 1
