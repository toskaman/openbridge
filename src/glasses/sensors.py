"""Bluetooth LE sport sensors: decoders for the standard GATT characteristics (Bluetooth SIG assigned numbers).

Pure functions from notification bytes to typed metrics, so they are unit-tested against the specification byte
layouts and work the same whether the bytes come from the phone (Companion) or from this PC (bleak).

  0x2A37 Heart Rate Measurement            -> heart_rate_bpm (+ RR intervals)
  0x2A53 RSC Measurement (running)          -> speed_mps, cadence_spm, stride_length_m, distance_m
  0x2A5B CSC Measurement (cycling)          -> speed_mps, cadence_rpm (from successive notifications)
  0x2A63 Cycling Power Measurement          -> power_w, cadence_rpm
  0x2AD2 Indoor Bike Data (FTMS)            -> speed_mps, cadence_rpm, distance_m, power_w, heart_rate_bpm
  0x2A19 Battery Level                      -> battery_pct
ANT+ is not decoded here: a phone has no ANT+ radio unless an adapter relays it.
"""
from __future__ import annotations

import struct
import time

from src.glasses.metrics import Observation

UUIDS = {
    'heart_rate': '00002a37-0000-1000-8000-00805f9b34fb',
    'rsc': '00002a53-0000-1000-8000-00805f9b34fb',
    'csc': '00002a5b-0000-1000-8000-00805f9b34fb',
    'cycling_power': '00002a63-0000-1000-8000-00805f9b34fb',
    'indoor_bike': '00002ad2-0000-1000-8000-00805f9b34fb',
    'battery': '00002a19-0000-1000-8000-00805f9b34fb',
}


class DecodeError(ValueError):
    pass


def _need(data, n):
    if len(data) < n:
        raise DecodeError('truncated notification')


def heart_rate(data: bytes) -> dict:
    _need(data, 2)
    flags = data[0]
    i = 1
    if flags & 0x01:
        _need(data, 3)
        bpm = struct.unpack_from('<H', data, i)[0]
        i += 2
    else:
        bpm = data[i]
        i += 1
    contact = {0b10: False, 0b11: True}.get((flags >> 1) & 0b11)
    if flags & 0x08:
        i += 2                                        # energy expended, unused here
    rr = []
    if flags & 0x10:
        while i + 1 < len(data):
            rr.append(struct.unpack_from('<H', data, i)[0] / 1024.0)
            i += 2
    return {'heart_rate_bpm': bpm, 'rr_s': rr, 'contact': contact}


def rsc(data: bytes) -> dict:
    _need(data, 4)
    flags = data[0]
    speed = struct.unpack_from('<H', data, 1)[0] / 256.0
    out = {'speed_mps': speed, 'cadence_spm': data[3], 'running': bool(flags & 0x04)}
    i = 4
    if flags & 0x01:
        _need(data, i + 2)
        out['stride_length_m'] = struct.unpack_from('<H', data, i)[0] / 100.0
        i += 2
    if flags & 0x02:
        _need(data, i + 4)
        out['distance_m'] = struct.unpack_from('<I', data, i)[0] / 10.0
    return out


def battery(data: bytes) -> dict:
    _need(data, 1)
    return {'battery_pct': min(100, data[0])}


def indoor_bike(data: bytes) -> dict:
    _need(data, 2)
    flags = struct.unpack_from('<H', data, 0)[0]
    i, out = 2, {}

    def take(fmt):
        nonlocal i
        size = struct.calcsize(fmt)
        _need(data, i + size)
        v = struct.unpack_from(fmt, data, i)[0]
        i += size
        return v
    if not flags & 0x0001:                            # bit 0 = "more data": speed present when it is 0
        out['speed_mps'] = take('<H') / 100.0 / 3.6
    if flags & 0x0002:
        take('<H')                                    # average speed
    if flags & 0x0004:
        out['cadence_rpm'] = take('<H') / 2.0
    if flags & 0x0008:
        take('<H')                                    # average cadence
    if flags & 0x0010:
        _need(data, i + 3)
        out['distance_m'] = data[i] | data[i + 1] << 8 | data[i + 2] << 16
        i += 3
    if flags & 0x0020:
        take('<h')                                    # resistance level
    if flags & 0x0040:
        out['power_w'] = max(0, take('<h'))
    if flags & 0x0080:
        take('<h')                                    # average power
    if flags & 0x0100:
        take('<H'); take('<H'); take('<B')            # expended energy: total, per hour, per minute
    if flags & 0x0200:
        out['heart_rate_bpm'] = take('<B')
    return out


class CSC:
    """Speed and cadence need two notifications: revolutions and event times are cumulative counters."""

    def __init__(self, wheel_circumference_m=2.105):
        self.circ = wheel_circumference_m
        self.wheel = self.crank = None

    def feed(self, data: bytes) -> dict:
        _need(data, 1)
        flags, i, out = data[0], 1, {}
        if flags & 0x01:
            _need(data, i + 6)
            revs, t = struct.unpack_from('<IH', data, i)
            i += 6
            if self.wheel:
                d_rev = (revs - self.wheel[0]) & 0xFFFFFFFF
                d_t = ((t - self.wheel[1]) & 0xFFFF) / 1024.0
                if d_t > 0 and d_rev < 1000:
                    out['speed_mps'] = d_rev * self.circ / d_t
                elif d_t == 0 and d_rev == 0:
                    out['speed_mps'] = 0.0
            self.wheel = (revs, t)
        if flags & 0x02:
            _need(data, i + 4)
            revs, t = struct.unpack_from('<HH', data, i)
            if self.crank:
                d_rev = (revs - self.crank[0]) & 0xFFFF
                d_t = ((t - self.crank[1]) & 0xFFFF) / 1024.0
                if d_t > 0 and d_rev < 100:
                    out['cadence_rpm'] = d_rev * 60.0 / d_t
                elif d_rev == 0:
                    out['cadence_rpm'] = 0.0
            self.crank = (revs, t)
        return out


class CyclingPower:
    def __init__(self):
        self.crank = None

    def feed(self, data: bytes) -> dict:
        _need(data, 4)
        flags, power = struct.unpack_from('<Hh', data, 0)
        i, out = 4, {'power_w': max(0, power)}
        if flags & 0x0001:
            _need(data, i + 1)
            out['balance_pct'] = data[i] / 2.0
            i += 1
        if flags & 0x0004:
            i += 2                                    # accumulated torque
        if flags & 0x0010:
            i += 6                                    # wheel revolutions + event time
        if flags & 0x0020:
            _need(data, i + 4)
            revs, t = struct.unpack_from('<HH', data, i)
            if self.crank:
                d_rev = (revs - self.crank[0]) & 0xFFFF
                d_t = ((t - self.crank[1]) & 0xFFFF) / 1024.0
                if d_t > 0 and d_rev < 100:
                    out['cadence_rpm'] = d_rev * 60.0 / d_t
            self.crank = (revs, t)
        return out


class Sensor:
    """One paired sensor: decodes its notifications into Observations for the metric store."""
    DECODERS = {'heart_rate': heart_rate, 'rsc': rsc, 'battery': battery, 'indoor_bike': indoor_bike}

    def __init__(self, kind, source_id, clock=time.time, **kw):
        if kind not in UUIDS:
            raise ValueError('unknown sensor kind %r' % kind)
        self.kind, self.source_id, self.clock = kind, source_id, clock
        self.stateful = CSC(**kw) if kind == 'csc' else CyclingPower() if kind == 'cycling_power' else None
        self.errors = 0
        self.last_seen = None

    def feed(self, data: bytes) -> list[Observation]:
        try:
            values = self.stateful.feed(data) if self.stateful else self.DECODERS[self.kind](data)
        except DecodeError:
            self.errors += 1
            return []
        now = self.clock()
        self.last_seen = now
        return [Observation(m, v, self.source_id, 'ble_' + self.kind, now)
                for m, v in values.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
                and m in ('heart_rate_bpm', 'speed_mps', 'cadence_rpm', 'cadence_spm', 'power_w', 'distance_m',
                          'stride_length_m', 'battery_pct')]
