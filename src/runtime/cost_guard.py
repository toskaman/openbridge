"""Command Center P0: cloud cost guard.

Local tiers are free. Cloud (high) needs explicit consent + an enabled kill
switch + budget headroom in the SAME reservations table the advisory broker
uses (one conservative ledger, no forked accounting). Estimates match the
broker's per-call reservation.
"""
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from src.ai.broker import RESERVATION_MICRO_USD

GLOBAL_CEILING_MICRO = 1_000_000


class CostBlocked(ValueError):
    pass


def estimate_usd(quality):
    if quality in ('low', 'medium'):
        return 0.0
    if quality in ('high', 'auto'):
        return RESERVATION_MICRO_USD / 1_000_000
    raise CostBlocked(f'unknown quality: {quality}')


def require_cloud(consent, cloud_enabled=True):
    if not cloud_enabled:
        raise CostBlocked('cloud is disabled by the kill switch')
    if consent is not True:
        raise CostBlocked('cloud needs explicit consent')


def _sums(db_path, observation_id):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS reservations (id INTEGER PRIMARY KEY, observation TEXT, reserved INTEGER, recorded REAL)')
        used = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE observation=?',
                          (observation_id,)).fetchone()[0]
        total = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations').fetchone()[0]
        return used, total


def check_budget(db_path, observation_id, ceiling_micro, amount_micro):
    used, total = _sums(db_path, observation_id)
    if used + amount_micro > ceiling_micro:
        raise CostBlocked('observation budget exhausted')
    if total + amount_micro > GLOBAL_CEILING_MICRO:
        raise CostBlocked('global conservative budget exhausted')
    return ceiling_micro - used - amount_micro


def admit(db_path, observation_id, ceiling_micro, amount_micro):
    """Atomic check-and-reserve: sums and insert happen inside one BEGIN
    IMMEDIATE transaction, so concurrent admissions can never overshoot."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS reservations (id INTEGER PRIMARY KEY, observation TEXT, reserved INTEGER, recorded REAL)')
        db.execute('BEGIN IMMEDIATE')
        used = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations WHERE observation=?',
                          (observation_id,)).fetchone()[0]
        total = db.execute('SELECT COALESCE(SUM(reserved),0) FROM reservations').fetchone()[0]
        if used + amount_micro > ceiling_micro:
            raise CostBlocked('observation budget exhausted')
        if total + amount_micro > GLOBAL_CEILING_MICRO:
            raise CostBlocked('global conservative budget exhausted')
        db.execute('INSERT INTO reservations(observation,reserved,recorded) VALUES(?,?,?)',
                   (observation_id, amount_micro, time.time()))
        return ceiling_micro - used - amount_micro


def reserve(db_path, observation_id, amount_micro):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS reservations (id INTEGER PRIMARY KEY, observation TEXT, reserved INTEGER, recorded REAL)')
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO reservations(observation,reserved,recorded) VALUES(?,?,?)',
                   (observation_id, amount_micro, time.time()))
