"""Device -> PC file transfer over the signed (and aead1-sealed) relay channel.

Flow: the owner shares a file into the Companion (Android share sheet); the Companion hashes it and lists an offer.
The PC never pulls anything the owner did not accept on the PC (owner path, CSRF). Accepted transfers are pulled in
bounded chunks (`read_chunk`), appended to a private `.part` file, resumed from the `.part` length after an
interruption, verified against the offered SHA-256, then atomically renamed into the private inbox. A failed hash
deletes the partial file. Quotas bound file size, inbox size and concurrent jobs; stale partial files are cleaned.
"""
import base64
import hashlib
import os
import re
import threading
import time
from pathlib import Path

from src.fabric import relay as fabric_relay

CHUNK = 96 * 1024                 # sealed + base64 twice stays under the 300 kB relay reply cap
MAX_FILE = 64 * 1024 * 1024
MAX_INBOX = 512 * 1024 * 1024
MAX_ACTIVE = 2
PART_TTL_S = 24 * 3600
MAX_OFFERS = 16
TRANSFER_ID = re.compile(r'^t[0-9a-f]{16,32}$')
SAFE_NAME = re.compile(r'[^A-Za-z0-9 ._()-]')


class TransferError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def safe_name(name):
    base = SAFE_NAME.sub('_', str(name or ''))[-120:].strip(' .') or 'file'
    return base if not base.startswith('.') else '_' + base


def validate_offers(params):
    offers = params.get('offers') if isinstance(params, dict) else None
    if not isinstance(offers, list) or len(offers) > MAX_OFFERS:
        raise fabric_relay.RelayError('Malformed transfer offers')
    out = []
    for o in offers:
        if not isinstance(o, dict) or not TRANSFER_ID.match(str(o.get('transfer_id', ''))):
            continue
        size = o.get('size')
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_FILE:
            continue
        if not fabric_relay.SHA256.match(str(o.get('sha256', ''))):
            continue
        out.append({'transfer_id': o['transfer_id'], 'name': safe_name(o.get('name')), 'size': size,
                    'sha256': o['sha256'], 'mime': str(o.get('mime', ''))[:80]})
    return out


class TransferManager:
    def __init__(self, server, inbox, clock=time.time):
        self.server, self.inbox, self.clock = server, Path(inbox), clock
        self._lock = threading.Lock()
        self.jobs = {}            # transfer_id -> job dict (public fields only in state())
        self.offers = {}          # transfer_id -> (relay_id, offer)

    # ---------- relay I/O ----------
    def _send(self, rid, op, params=None):
        r = self.server.relays.relays.get(rid)
        if r is None:
            raise fabric_relay.RelayError('Unknown relay')
        msg = fabric_relay.command(r['key'], rid, op, params)
        try:
            return fabric_relay.verify(r['key'], r['send'](r, msg), r['seen']).get('params', {})
        except (OSError, TimeoutError) as e:
            raise fabric_relay.RelayError('Relay unreachable: %s' % type(e).__name__) from None

    def refresh_offers(self):
        found = {}
        for rid, r in list(self.server.relays.relays.items()):
            if 'file_offer' not in r.get('capabilities', ()) or not r.get('online'):
                continue
            try:
                for o in validate_offers(self._send(rid, 'get_transfers')):
                    found[o['transfer_id']] = (rid, o)
            except fabric_relay.RelayError:
                continue
        with self._lock:
            self.offers = found
        return [dict(o, relay_id=rid) for rid, o in found.values()]

    # ---------- owner actions ----------
    def _inbox_bytes(self):
        if not self.inbox.exists():
            return 0
        return sum(p.stat().st_size for p in self.inbox.iterdir() if p.is_file())

    def accept(self, relay_id, transfer_id, consent=False):
        if consent is not True:
            raise TransferError(400, 'consent: true is required to receive a file')
        with self._lock:
            hit = self.offers.get(transfer_id)
            if hit is None or hit[0] != relay_id:
                raise TransferError(404, 'No such offer from this device (refresh offers first)')
            job = self.jobs.get(transfer_id)
            if job and job['state'] in ('RUNNING', 'RECEIVED'):
                return self._public(job)
            if sum(1 for j in self.jobs.values() if j['state'] == 'RUNNING') >= MAX_ACTIVE:
                raise TransferError(429, 'Too many transfers in progress')
            offer = hit[1]
            if self._inbox_bytes() + offer['size'] > MAX_INBOX:
                raise TransferError(507, 'Inbox quota exceeded; free space first')
            job = {'transfer_id': transfer_id, 'relay_id': relay_id, 'name': offer['name'], 'size': offer['size'],
                   'sha256': offer['sha256'], 'state': 'RUNNING', 'received': 0, 'error': None, 'path': None,
                   'cancel': threading.Event(), 'started_at': self.clock()}
            self.jobs[transfer_id] = job
        threading.Thread(target=self._run, args=(job,), name='transfer-' + transfer_id, daemon=True).start()
        return self._public(job)

    def cancel(self, transfer_id):
        with self._lock:
            job = self.jobs.get(transfer_id)
        if job is None:
            raise TransferError(404, 'Unknown transfer')
        job['cancel'].set()
        if job['state'] != 'RUNNING':
            self._part(job).unlink(missing_ok=True)
            job['state'] = 'CANCELLED' if job['state'] != 'RECEIVED' else job['state']
        return self._public(job)

    def _part(self, job):
        return self.inbox / ('.%s.part' % job['transfer_id'])

    def _final(self, job):
        stem, dot, ext = job['name'].rpartition('.')
        if not dot:
            stem, ext = job['name'], ''
        for i in range(0, 1000):
            cand = self.inbox / ((stem if i == 0 else '%s (%d)' % (stem, i)) + ('.' + ext if ext else ''))
            if not cand.exists():
                return cand
        raise TransferError(409, 'Too many files with this name')

    def _run(self, job):
        part = self._part(job)
        try:
            self.inbox.mkdir(parents=True, exist_ok=True)
            offset = part.stat().st_size if part.exists() else 0       # resume after an interruption
            if offset > job['size']:
                part.unlink(); offset = 0
            with open(part, 'ab') as f:
                while offset < job['size']:
                    if job['cancel'].is_set():
                        raise TransferError(499, 'cancelled')
                    want = min(CHUNK, job['size'] - offset)
                    p = self._send(job['relay_id'], 'read_chunk', {'transfer_id': job['transfer_id'], 'offset': offset, 'length': want})
                    if p.get('transfer_id') != job['transfer_id'] or p.get('offset') != offset:
                        raise fabric_relay.RelayError('chunk does not match the request')
                    data = base64.b64decode(str(p.get('data', '')), validate=True)
                    if not 0 < len(data) <= want:
                        raise fabric_relay.RelayError('chunk length out of bounds')
                    f.write(data); f.flush()
                    offset += len(data)
                    job['received'] = offset
                os.fsync(f.fileno())
            h = hashlib.sha256()
            with open(part, 'rb') as f:
                for block in iter(lambda: f.read(1 << 20), b''):
                    h.update(block)
            if h.hexdigest() != job['sha256']:
                part.unlink(missing_ok=True)
                raise TransferError(422, 'SHA-256 mismatch; partial file deleted')
            final = self._final(job)
            os.replace(part, final)
            job.update(state='RECEIVED', path=str(final))
            self._finish(job, 'received')
        except TransferError as e:
            job.update(state='CANCELLED' if e.status == 499 else 'FAILED', error=str(e))
            if e.status == 499:
                part.unlink(missing_ok=True)
            self._finish(job, 'cancelled' if e.status == 499 else 'failed')
        except (fabric_relay.RelayError, ValueError, OSError) as e:
            # Network or device trouble: keep the partial file, the owner can resume (same accept call).
            job.update(state='INTERRUPTED', error='%s: %s' % (type(e).__name__, str(e)[:120]))

    def _finish(self, job, status):
        try:
            self._send(job['relay_id'], 'finish_transfer', {'transfer_id': job['transfer_id'], 'status': status})
        except fabric_relay.RelayError:
            pass

    def cleanup(self, now=None):
        now = now if now is not None else time.time()
        removed = 0
        if self.inbox.exists():
            for p in self.inbox.glob('.*.part'):
                if now - p.stat().st_mtime > PART_TTL_S:
                    p.unlink(missing_ok=True); removed += 1
        return removed

    @staticmethod
    def _public(job):
        return {k: job[k] for k in ('transfer_id', 'relay_id', 'name', 'size', 'sha256', 'state', 'received', 'error', 'path')}

    def state(self):
        with self._lock:
            return {'offers': [dict(o, relay_id=rid) for rid, o in self.offers.values()],
                    'jobs': [self._public(j) for j in self.jobs.values()]}
