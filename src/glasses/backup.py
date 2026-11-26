"""ENGO / ActiveLook by Microoled — Firmware Metadata, Settings & Flash-Catalog Backup.

What can be backed up over BLE / USB from ENGO 1 / 2 / 3 smart glasses:
  1. Complete Device Information Service (DIS 0x180A): firmware revision (0x2A26),
     hardware/software revisions (0x2A27/0x2A28), model, manufacturer, serial.
  2. ActiveLook protocol queries (ENGO / ActiveLook by Microoled):
     - 0x06 vers       : firmware version, build year/week, MCU serial
     - 0x0A settings   : optical x/y shift, luma, ALS, IR gesture sensor state
     - 0x05 battery    : battery %
     - 0xE3 rdDevInfo  : platform, manufacturer, model, firmware, serial
     - 0xD3 cfgList    : 3 MB NOR flash configuration containers
     - 0xD7 cfgFreeSpace / 0xD8 cfgGetNb
     - 0x64 layoutList, 0x47 imgList, 0x50 fontList
  3. Re-playable `settings_restore.bin` frame bundle + optional archival of an
     official SUOTA firmware image (.bin/.img/.zip) obtained from ENGO / ActiveLook
     developer channels.

Note on raw executable flash extraction:
  Dialog/Renesas DA1469x (ActiveLook) and BLE SUOTA (0xFEF5) only allow signed
  Central -> Glasses firmware writes; no BLE opcode reads executable MCU flash.
  This tool archives every readable identity, config catalog, setting and raw TX
  frame into a timestamped SHA-256-verified ZIP archive.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.adapters import activelook as AL

DIS_CHARS = {
    'model_number': '00002a24-0000-1000-8000-00805f9b34fb',
    'serial_number': '00002a25-0000-1000-8000-00805f9b34fb',
    'firmware_revision': '00002a26-0000-1000-8000-00805f9b34fb',
    'hardware_revision': '00002a27-0000-1000-8000-00805f9b34fb',
    'software_revision': '00002a28-0000-1000-8000-00805f9b34fb',
    'manufacturer': '00002a29-0000-1000-8000-00805f9b34fb',
}
BATTERY_CHAR_UUID = '00002a19-0000-1000-8000-00805f9b34fb'
SUOTA_SERVICE_UUID = '0000fef5-0000-1000-8000-00805f9b34fb'


def default_backup_root() -> Path:
    base = os.environ.get('OPENBRIDGE_GLASSES_BACKUP_DIR')
    if base:
        return Path(base)
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'engo_backups'


def decode_tx_frame(frame: bytes) -> Optional[tuple[int, bytes, bytes]]:
    """Decode one ActiveLook 0xFF [CMD] [FMT] [LEN] [QID] [DATA] 0xAA frame."""
    if len(frame) < 5 or frame[0] != 0xFF or frame[-1] != 0xAA:
        return None
    cmd = frame[1]
    fmt = frame[2]
    wide = bool(fmt & 0x10) or bool(fmt & 0x20)
    qid_len = (fmt >> 1) & (0x07 if (fmt & 0x10) else 0x0F)
    hdr = 5 if wide else 4
    if len(frame) < hdr + qid_len + 1:
        return None
    total_len = struct.unpack('>H', frame[3:5])[0] if wide else frame[3]
    if total_len != len(frame):
        return None
    qid = frame[hdr:hdr + qid_len]
    data = frame[hdr + qid_len:-1]
    return cmd, qid, data


def reassemble_tx_frames(chunks: list[bytes]) -> list[bytes]:
    """Reassemble fragmented BLE TX notifications into complete 0xFF...0xAA ActiveLook frames."""
    buf = bytearray()
    for ch in chunks:
        buf.extend(ch)
    frames: list[bytes] = []
    i = 0
    n = len(buf)
    while i < n:
        if buf[i] != 0xFF:
            nxt = buf.find(b'\xFF', i + 1)
            if nxt < 0:
                frames.append(bytes(buf[i:]))
                break
            frames.append(bytes(buf[i:nxt]))
            i = nxt
            continue
        if i + 4 > n:
            frames.append(bytes(buf[i:]))
            break
        fmt = buf[i + 2]
        wide = bool(fmt & 0x10) or bool(fmt & 0x20)
        if wide and i + 5 > n:
            frames.append(bytes(buf[i:]))
            break
        total_len = struct.unpack('>H', buf[i + 3:i + 5])[0] if wide else buf[i + 3]
        if total_len >= 5 and i + total_len <= n and buf[i + total_len - 1] == 0xAA:
            frames.append(bytes(buf[i:i + total_len]))
            i += total_len
        else:
            nxt = buf.find(b'\xFF', i + 1)
            if nxt < 0:
                frames.append(bytes(buf[i:]))
                break
            frames.append(bytes(buf[i:nxt]))
            i = nxt
    return frames


def decode_payload(cmd: int, data: bytes) -> dict[str, Any]:
    """Decode an ActiveLook TX response payload for backup metadata."""
    if cmd == 0x05 and len(data) >= 1:
        return {'battery_pct': int(data[0])}
    if cmd == 0x06 and len(data) >= 9:
        fw = '.'.join(str(b) for b in data[:4])
        year = 2000 + int(data[4])
        week = int(data[5])
        serial = int.from_bytes(data[6:9], 'big')
        return {'fw_version': fw, 'build_year': year, 'build_week': week, 'serial_int': serial,
                'serial_hex': data[6:9].hex()}
    if cmd == 0x0A:
        if len(data) >= 7:
            x, y, luma, als, gesture = struct.unpack('>hhBBB', data[:7])
            return {'shift_x': x, 'shift_y': y, 'luma': luma, 'als': bool(als), 'gesture': bool(gesture)}
        if len(data) >= 5:
            x, y = struct.unpack('>bb', data[:2])
            return {'shift_x': x, 'shift_y': y, 'luma': data[2], 'als': bool(data[3]), 'gesture': bool(data[4])}
    if cmd == 0x47:
        imgs = []
        for i in range(0, len(data) - 4, 5):
            img_id, w, h = struct.unpack('>BHH', data[i:i + 5])
            imgs.append({'id': img_id, 'width': w, 'height': h})
        return {'images': imgs}
    if cmd == 0x50:
        fonts = [{'id': data[i], 'height': data[i + 1]} for i in range(0, len(data) - 1, 2)]
        return {'fonts': fonts}
    if cmd == 0x64:
        return {'layout_ids': list(data)}
    if cmd == 0xD7 and len(data) >= 8:
        total_b, free_b = struct.unpack('>II', data[:8])
        return {'total_space_bytes': total_b, 'free_space_bytes': free_b}
    if cmd == 0xD7 and len(data) >= 4:
        return {'free_space_bytes': struct.unpack('>I', data[:4])[0]}
    if cmd == 0xD8 and len(data) >= 1:
        return {'config_count': int(data[0])}
    if cmd == 0xD3:
        configs = []
        pos = 0
        while pos < len(data):
            nul = data.find(b'\x00', pos)
            if nul < 0 or nul + 12 > len(data):
                break
            cname = data[pos:nul].decode('utf-8', errors='replace')
            size_b, ver = struct.unpack('>II', data[nul + 1:nul + 9])
            usage, install, system = data[nul + 9], data[nul + 10], data[nul + 11]
            configs.append({'name': cname, 'size_bytes': size_b, 'version': ver,
                            'usage_count': usage, 'install_count': install, 'is_system': bool(system)})
            pos = nul + 12
        return {'configs': configs, 'cfg_list_hex': data.hex(), 'size_bytes': len(data)}
    if cmd == 0xE3:
        txt = data.rstrip(b'\x00').decode('utf-8', errors='replace')
        return {'dev_info_text': txt, 'raw_hex': data.hex()}
    return {'raw_hex': data.hex()}


def build_restore_frames(settings: dict[str, Any]) -> bytes:
    """Build replayable ActiveLook binary frames to restore optical shift, luma, ALS and gesture."""
    frames = bytearray()
    if 'shift_x' in settings and 'shift_y' in settings:
        frames += AL.encode_packet(0x09, struct.pack('>hh', int(settings['shift_x']), int(settings['shift_y'])))
    if 'luma' in settings:
        frames += AL.cmd_luma(int(settings['luma']))
    if 'gesture' in settings:
        frames += AL.encode_packet(0x21, bytes([0x01 if settings['gesture'] else 0x00]))
    if 'als' in settings:
        frames += AL.encode_packet(0x22, bytes([0x01 if settings['als'] else 0x00]))
    return bytes(frames)


def _backup_queries() -> list[tuple[str, bytes]]:
    """Ordered ActiveLook read-only inspection packets for ENGO / ActiveLook by Microoled."""
    return [
        ('vers', AL.encode_packet(0x06)),
        ('battery', AL.encode_packet(0x05)),
        ('settings', AL.encode_packet(0x0A)),
        ('rdDevInfo_platform', AL.encode_packet(0xE3, bytes([0]))),
        ('rdDevInfo_manufacturer', AL.encode_packet(0xE3, bytes([1]))),
        ('rdDevInfo_hwid', AL.encode_packet(0xE3, bytes([2]))),
        ('rdDevInfo_model', AL.encode_packet(0xE3, bytes([3]))),
        ('rdDevInfo_fw', AL.encode_packet(0xE3, bytes([5]))),
        ('rdDevInfo_serial', AL.encode_packet(0xE3, bytes([6]))),
        ('cfgFreeSpace', AL.encode_packet(0xD7)),
        ('cfgList', AL.encode_packet(0xD3)),
        ('layoutList', AL.encode_packet(0x64)),
        ('imgList', AL.encode_packet(0x47)),
        ('fontList', AL.encode_packet(0x50)),
    ]


def write_backup_archive(
    out_dir: Path,
    dis: dict[str, Any],
    tx_frames: list[bytes],
    device_meta: dict[str, Any],
    fw_package: Optional[Path] = None,
) -> dict[str, Any]:
    """Decode collected BLE DIS + ActiveLook TX responses and write a verified backup archive."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
    bundle_dir = out_dir / f'engo_activelook_backup_{stamp}'
    bundle_dir.mkdir(parents=True, exist_ok=True)

    decoded: dict[str, Any] = {}
    rd_dev_info: list[dict[str, Any]] = []
    raw_records: list[dict[str, Any]] = []

    for frame in reassemble_tx_frames(tx_frames):
        parsed = decode_tx_frame(frame)
        if parsed is None:
            raw_records.append({'raw_hex': frame.hex(), 'valid': False})
            continue
        cmd, qid, data = parsed
        info = decode_payload(cmd, data)
        raw_records.append({'cmd': f'0x{cmd:02X}', 'qid': qid.hex(), 'data_hex': data.hex(), 'decoded': info})
        if cmd == 0xE3:
            rd_dev_info.append(info)
        elif cmd == 0x06:
            decoded['vers'] = info
        elif cmd == 0x0A:
            decoded['settings'] = info
        elif cmd == 0x05:
            decoded['battery'] = info
        elif cmd == 0x47:
            decoded['images'] = info.get('images', [])
        elif cmd == 0x50:
            decoded['fonts'] = info.get('fonts', [])
        elif cmd == 0x64:
            decoded['layout_ids'] = info.get('layout_ids', [])
        elif cmd == 0xD3:
            decoded['cfg_list'] = info
        elif cmd == 0xD7:
            decoded['cfg_free_space'] = info
        elif cmd == 0xD8:
            decoded['cfg_count'] = info

    if rd_dev_info:
        decoded['rd_dev_info'] = rd_dev_info

    restore_bytes = build_restore_frames(decoded.get('settings') or {})
    if restore_bytes:
        (bundle_dir / 'settings_restore.bin').write_bytes(restore_bytes)

    archived_fw = None
    if fw_package is not None:
        fw_path = Path(fw_package)
        if not fw_path.is_file():
            raise FileNotFoundError(f'Firmware package not found: {fw_path}')
        dest_fw = bundle_dir / fw_path.name
        shutil.copy2(fw_path, dest_fw)
        archived_fw = {
            'filename': fw_path.name,
            'size_bytes': dest_fw.stat().st_size,
            'sha256': hashlib.sha256(dest_fw.read_bytes()).hexdigest(),
        }

    manifest = {
        'schema': 'openbridge.engo.backup/1',
        'partners': ['ENGO', 'ActiveLook by Microoled'],
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'device': device_meta,
        'ble_dis': dis,
        'activelook': decoded,
        'settings_restore_bytes': len(restore_bytes),
        'firmware_package': archived_fw,
        'raw_flash_dump_note': (
            'ActiveLook (Dialog/Renesas DA1469x) and SUOTA (0xFEF5) restrict raw MCU flash '
            'readback over BLE; this archive backs up DIS firmware identity, ActiveLook '
            'config/layout/font/image catalogs, raw TX frames, and replayable settings.'
        ),
    }

    (bundle_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (bundle_dir / 'raw_frames.jsonl').write_text(
        '\n'.join(json.dumps(r) for r in raw_records) + ('\n' if raw_records else ''),
        encoding='utf-8',
    )

    zip_path = out_dir / f'engo_activelook_backup_{stamp}.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(bundle_dir.rglob('*')):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(bundle_dir))

    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    return {
        'partners': ['ENGO', 'ActiveLook by Microoled'],
        'archive_zip': str(zip_path),
        'archive_sha256': zip_sha,
        'bundle_dir': str(bundle_dir),
        'firmware_revision': dis.get('firmware_revision') or (decoded.get('vers') or {}).get('fw_version'),
        'suota_present': bool(device_meta.get('suota_present')),
        'tx_frames_captured': len(tx_frames),
        'settings_restore_bytes': len(restore_bytes),
        'firmware_package': archived_fw,
    }


async def _ble_backup_async(
    out_dir: Path,
    address: Optional[str] = None,
    name_hint: str = 'ENGO',
    fw_package: Optional[Path] = None,
    log_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    from bleak import BleakClient, BleakScanner

    log_fn('[ENGO / ActiveLook by Microoled] Scanning BLE for ENGO smart glasses...')
    dev = None
    if not address:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.name or '').upper().startswith(name_hint.upper())
            or AL.SERVICE_UUID in [u.lower() for u in (ad.service_uuids or [])],
            timeout=20.0,
        )
        if dev is None:
            raise OSError('No ENGO / ActiveLook glasses found nearby over BLE (ensure glasses are on and not tethered to a phone)')
        address = dev.address

    dis: dict[str, Any] = {}
    tx_frames: list[bytes] = []
    suota_present = False
    dev_name = getattr(dev, 'name', None) or name_hint

    log_fn(f'[ENGO / ActiveLook by Microoled] Connecting to {dev_name} ({address})...')
    async with BleakClient(address) as client:
        services = client.services
        suota_present = any(s.uuid.lower() == SUOTA_SERVICE_UUID for s in services)

        for key, uuid in DIS_CHARS.items():
            try:
                raw = await client.read_gatt_char(uuid)
                dis[key] = raw.decode('utf-8', errors='replace').rstrip('\x00')
            except Exception:
                pass
        try:
            batt = await client.read_gatt_char(BATTERY_CHAR_UUID)
            if batt:
                dis['battery_level_gatt'] = int(batt[0])
        except Exception:
            pass

        def _on_tx(_sender, data: bytearray):
            tx_frames.append(bytes(data))

        await client.start_notify(AL.TX_CHAR_UUID, _on_tx)
        for label, pkt in _backup_queries():
            log_fn(f'[ENGO / ActiveLook by Microoled] Querying {label}...')
            await client.write_gatt_char(AL.RX_CHAR_UUID, pkt, response=False)
            await asyncio.sleep(0.18)
        await asyncio.sleep(0.5)
        try:
            await client.stop_notify(AL.TX_CHAR_UUID)
        except Exception:
            pass

    meta = {
        'name': dev_name,
        'address': address,
        'mtu': getattr(client, 'mtu_size', None),
        'suota_present': suota_present,
    }
    res = write_backup_archive(out_dir, dis, tx_frames, meta, fw_package=fw_package)
    log_fn(f"[ENGO / ActiveLook by Microoled] Backup saved: {res['archive_zip']} (sha256={res['archive_sha256'][:16]}...)")
    return res


def backup_via_relay(
    out_dir: Optional[str | Path] = None,
    address: Optional[str] = None,
    name_hint: str = 'ENGO',
    fw_package: Optional[str | Path] = None,
    serial: Optional[str] = None,
    port: int = 47800,
    log_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Back up ENGO / ActiveLook by Microoled glasses through a paired Android Companion over ADB/LAN."""
    from src.fabric import aead as A, relay as R
    from src.fabric.relay_store import default_owner_store

    store = default_owner_store()
    recs = store.load()
    candidates = [row for row in recs if 'glasses_link' in (row[3].get('capabilities') or []) or row[1] == serial]
    if not candidates:
        candidates = list(recs)
    if not candidates:
        raise OSError('No paired Android Companion found in OpenBridge RelayStore')

    # Pick matching ADB serial if provided, else first connected ADB serial matching store
    chosen = None
    if serial:
        chosen = next((row for row in candidates if row[1] == serial), None)
    if chosen is None:
        adb_out = ''
        try:
            adb_out = subprocess.check_output(['adb', 'devices'], text=True, timeout=5)
        except Exception:
            pass
        for row in candidates:
            if row[1] and row[1] in adb_out:
                chosen = row
                break
    if chosen is None:
        chosen = candidates[0]

    rid, dev_serial, key, _declared, aead_v = chosen
    if dev_serial and ':' not in dev_serial and not dev_serial.startswith('adb-'):
        subprocess.run(['adb', '-s', dev_serial, 'forward', f'tcp:{port}', f'tcp:{port}'], check=False, capture_output=True)
    elif dev_serial:
        subprocess.run(['adb', '-s', dev_serial, 'forward', f'tcp:{port}', f'tcp:{port}'], check=False, capture_output=True)

    base_url = f'http://127.0.0.1:{port}'
    send = R.http_transport(base_url, timeout=15)
    if aead_v:
        send = A.encrypting_send(send, rid)
    r_ctx = {'key': key, 'seen': {}}

    def _call(op: str, params: Optional[dict] = None) -> dict[str, Any]:
        rep = send(r_ctx, R.command(key, rid, op, params))
        return R.verify(key, rep, r_ctx['seen']).get('params') or {}

    log_fn(f'[ENGO / ActiveLook by Microoled] Connecting via paired phone relay {rid} ({dev_serial})...')
    conn_params: dict[str, Any] = {'name_hint': name_hint, 'seconds': 10}
    if address:
        conn_params['address'] = address.upper()
    conn: dict[str, Any] = {}
    for attempt in range(2):
        try:
            conn = _call('glasses_connect', conn_params)
            break
        except Exception:
            if attempt == 1:
                raise
            time.sleep(1.2)
    log_fn(f"[ENGO / ActiveLook by Microoled] Connected to {conn.get('name')} ({conn.get('address')}) mtu={conn.get('mtu')}")

    info = _call('glasses_info')
    dis = info.get('dis') or {}
    suota_present = bool(info.get('suota_present'))
    svc_uuids = [str(s.get('uuid', '')).lower() for s in (info.get('services') or [])]
    mcumgr_smp_present = '8d53dc1d-1db7-4cd3-868b-8a527460aa84' in svc_uuids

    tx_chunks: list[bytes] = []
    # Flush stale events before querying
    _call('glasses_events', {'wait_ms': 20})
    for label, pkt in _backup_queries():
        log_fn(f'[ENGO / ActiveLook by Microoled] Querying {label}...')
        w_res = _call('glasses_write', {'chunks': [base64.b64encode(pkt).decode('ascii')]})
        got = [bytes.fromhex(ev['v']) for ev in (w_res.get('events') or []) if ev.get('t') == 'tx' and ev.get('v')]
        tx_chunks.extend(got)
        for _ in range(4):
            ev_res = _call('glasses_events', {'wait_ms': 250})
            more = [bytes.fromhex(ev['v']) for ev in (ev_res.get('events') or []) if ev.get('t') == 'tx' and ev.get('v')]
            tx_chunks.extend(more)
            if not more and (got or label not in ('imgList', 'cfgList')):
                break
            got.extend(more)
    tx_frames = reassemble_tx_frames(tx_chunks)

    meta = {
        'name': conn.get('name') or name_hint,
        'address': conn.get('address') or address,
        'mtu': conn.get('mtu'),
        'suota_present': suota_present,
        'mcumgr_smp_present': mcumgr_smp_present,
        'gatt_services': info.get('services') or [],
        'via_relay': rid,
        'phone_serial': dev_serial,
    }
    target = Path(out_dir) if out_dir else default_backup_root()
    fw = Path(fw_package) if fw_package else None
    res = write_backup_archive(target, dis, tx_frames, meta, fw_package=fw)
    log_fn(f"[ENGO / ActiveLook by Microoled] Backup saved: {res['archive_zip']} (sha256={res['archive_sha256'][:16]}...)")
    return res


def backup_glasses(
    out_dir: Optional[str | Path] = None,
    address: Optional[str] = None,
    name_hint: str = 'ENGO',
    fw_package: Optional[str | Path] = None,
    via_phone: bool = False,
    log_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Connect over BLE (or via paired phone Companion) to ENGO / ActiveLook glasses and archive firmware identity & configs."""
    if via_phone:
        return backup_via_relay(out_dir=out_dir, address=address, name_hint=name_hint, fw_package=fw_package, log_fn=log_fn)
    target = Path(out_dir) if out_dir else default_backup_root()
    fw = Path(fw_package) if fw_package else None
    try:
        return asyncio.run(_ble_backup_async(target, address=address, name_hint=name_hint, fw_package=fw, log_fn=log_fn))
    except Exception as e:
        if 'No Bluetooth adapter' in str(e) or 'Bluetooth' in type(e).__name__:
            log_fn('[ENGO / ActiveLook by Microoled] PC has no Bluetooth adapter; falling back to paired phone relay...')
            return backup_via_relay(out_dir=out_dir, address=address, name_hint=name_hint, fw_package=fw, log_fn=log_fn)
        raise


async def _ble_restore_settings_async(
    frames_bytes: bytes,
    address: Optional[str] = None,
    name_hint: str = 'ENGO',
) -> dict[str, Any]:
    from bleak import BleakClient, BleakScanner

    if not address:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.name or '').upper().startswith(name_hint.upper())
            or AL.SERVICE_UUID in [u.lower() for u in (ad.service_uuids or [])],
            timeout=20.0,
        )
        if dev is None:
            raise OSError('No ENGO / ActiveLook glasses found nearby over BLE')
        address = dev.address

    async with BleakClient(address) as client:
        await client.write_gatt_char(AL.RX_CHAR_UUID, frames_bytes, response=False)
        await asyncio.sleep(0.25)
    return {'partners': ['ENGO', 'ActiveLook by Microoled'], 'address': address, 'bytes_written': len(frames_bytes)}


def restore_settings(
    backup_path: str | Path,
    address: Optional[str] = None,
    name_hint: str = 'ENGO',
) -> dict[str, Any]:
    """Replay saved `settings_restore.bin` (shift/luma/gesture/als) onto ENGO / ActiveLook glasses."""
    p = Path(backup_path)
    if p.is_dir():
        raw = (p / 'settings_restore.bin').read_bytes()
    elif p.is_file() and p.suffix.lower() == '.zip':
        with zipfile.ZipFile(p, 'r') as zf:
            raw = zf.read('settings_restore.bin')
    elif p.is_file():
        raw = p.read_bytes()
    else:
        raise FileNotFoundError(f'Backup not found: {p}')
    if not raw:
        raise ValueError('settings_restore.bin is empty')
    return asyncio.run(_ble_restore_settings_async(raw, address=address, name_hint=name_hint))
