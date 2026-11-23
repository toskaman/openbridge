"""Messages for the glasses: notifications from the phone (Discord, Telegram, SMS, Messages...).

The Companion app reads the phone's notifications (Android notification access, granted by the owner) for the apps
the owner allowed, and hands them to the PC over the paired, encrypted relay. Nothing is sent anywhere else, nothing
is stored on disk: the inbox lives in memory and holds the last MAX_ITEMS messages.

Privacy modes (owner setting): 'full' shows sender and text, 'sender' shows only who wrote, 'off' shows nothing.
"""
from __future__ import annotations

import hashlib
import threading
import time
import unicodedata

MAX_ITEMS = 50
DEDUPE_S = 600
MAX_SENDER, MAX_TEXT = 40, 400

# package -> (label, badge letter). The default allowlist is the apps the owner asked for; others can be added.
APPS = {
    'com.discord': ('Discord', 'D'),
    'org.telegram.messenger': ('Telegram', 'T'),
    'org.telegram.messenger.web': ('Telegram', 'T'),
    'org.thunderdog.challegram': ('Telegram X', 'T'),
    'com.google.android.apps.messaging': ('Messages', 'M'),
    'com.samsung.android.messaging': ('Messages', 'M'),
    'com.android.mms': ('SMS', 'S'),
    'com.android.messaging': ('SMS', 'S'),
    'com.whatsapp': ('WhatsApp', 'W'),
    'org.thoughtcrime.securesms': ('Signal', 'S'),
}
DEFAULT_ALLOWED = ('com.discord', 'org.telegram.messenger', 'org.telegram.messenger.web', 'org.thunderdog.challegram',
                   'com.google.android.apps.messaging', 'com.samsung.android.messaging', 'com.android.mms',
                   'com.android.messaging')


def clean(text, limit):
    """Printable, single-spaced, bounded. Removes control and bidi-override characters."""
    out = []
    for ch in str(text or ''):
        cat = unicodedata.category(ch)
        if cat in ('Cc', 'Cf', 'Co', 'Cs'):
            out.append(' ')
        else:
            out.append(ch)
    return ' '.join(''.join(out).split())[:limit]


class Inbox:
    def __init__(self, allowed=DEFAULT_ALLOWED, privacy='full', clock=time.time):
        self.allowed = set(allowed)
        self.privacy = privacy
        self.clock = clock
        self.items = []                 # newest first
        self._seen = {}                 # fingerprint -> time
        self._lock = threading.Lock()

    def add(self, n):
        """n: {package, sender, text, time?, key?}. Returns the stored item, or None when filtered."""
        pkg = str(n.get('package') or '')
        if pkg not in self.allowed or self.privacy == 'off':
            return None
        sender, text = clean(n.get('sender'), MAX_SENDER), clean(n.get('text'), MAX_TEXT)
        if not sender and not text:
            return None
        now = self.clock()
        fp = hashlib.sha256(('%s\x00%s\x00%s' % (pkg, sender, text)).encode('utf-8')).hexdigest()[:16]
        label, letter = APPS.get(pkg, (pkg.rsplit('.', 1)[-1].capitalize(), pkg[:1].upper() or '?'))
        with self._lock:
            for k, t in list(self._seen.items()):
                if now - t > DEDUPE_S:
                    del self._seen[k]
            if fp in self._seen:          # Android re-posts the same notification when it updates
                return None
            self._seen[fp] = now
            item = {'id': fp, 'package': pkg, 'app': label, 'letter': letter, 'sender': sender or label,
                    'text': text, 'time': float(n.get('time') or now), 'read': False}
            self.items.append(item)
            self.items.sort(key=lambda i: -i['time'])        # newest first, whatever the arrival order
            del self.items[MAX_ITEMS:]
        return item

    def shown(self, item):
        """What the glasses may display for an item under the privacy mode."""
        if self.privacy == 'sender':
            return dict(item, text='New message')
        return item

    def unread(self):
        with self._lock:
            return sum(1 for i in self.items if not i['read'])

    def list(self):
        with self._lock:
            return [self.shown(i) for i in self.items]

    def mark_read(self, item_id):
        with self._lock:
            for i in self.items:
                if i['id'] == item_id:
                    i['read'] = True

    def clear(self):
        with self._lock:
            self.items.clear()
