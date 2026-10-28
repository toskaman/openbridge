"""Command Center P0: typed NL commands submitted from paired Companions.

A Companion with the `command_submit` capability queues short typed commands;
the PC polls them over the existing signed relay channel, parses them with
LOCAL tiers only (never cloud from a device), stores the intent for owner
review, and reports the parse outcome back to the device. Nothing here
approves or executes: privileged dispatch happens only through the PC-side
approve/execute flow with fresh owner consent.
"""
import threading

from src.fabric import relay as fabric_relay

MAX_PENDING = 64


class CompanionCommands:
    def __init__(self, server, low=None, medium=None):
        self.server = server
        self._low, self._medium = low, medium
        self.pending = {}    # request_id -> {relay_id, text, lang, intent}
        self._order = []
        self._lock = threading.Lock()

    def _send(self, rid, op, params=None):
        r = self.server.relays.relays[rid]
        msg = fabric_relay.command(r['key'], rid, op, params)
        try:
            return fabric_relay.verify(r['key'], r['send'](r, msg), r['seen']).get('params', {})
        except (OSError, TimeoutError):
            r['online'] = False
            raise fabric_relay.RelayError('Relay unreachable') from None

    def _report_text(self, doc):
        st = doc['status']
        if st == 'resolved':
            return f"{doc['skill_id']} ready — review on this PC"
        if st == 'needs_clarification':
            return str(doc.get('clarifying_question') or 'Clarification needed')
        amb = (doc.get('ambiguities') or ['no detail'])
        return f"{'Unsupported' if st == 'unsupported' else 'Escalation needed'}: {amb[0]}"

    def poll_once(self):
        from src.runtime import command as C
        from src.runtime import nl_router as N
        low = self._low or C._low(self.server)
        medium = self._medium or C._medium(self.server)
        relays = getattr(getattr(self.server, 'relays', None), 'relays', None) or {}
        new = 0
        for rid, r in relays.items():
            if 'command_submit' not in r.get('capabilities', ()):
                continue
            if not r.get('online') or r.get('busy'):
                continue
            try:
                cmds = fabric_relay.validate_commands(self._send(rid, 'get_commands'))
            except fabric_relay.RelayError:
                continue
            for c in cmds:
                with self._lock:
                    if c['request_id'] in self.pending:
                        continue
                quality = c['quality'] if c['quality'] in ('low', 'medium') else 'auto'
                doc = N.parse(c['text'], c['lang'], quality, low, None, medium,
                              cloud_allowed=False)
                with self._lock:
                    self.pending[c['request_id']] = {'relay_id': rid, 'text': c['text'],
                                                     'lang': c['lang'], 'intent': doc}
                    self._order.append(c['request_id'])
                    while len(self._order) > MAX_PENDING:
                        self.pending.pop(self._order.pop(0), None)
                new += 1
                try:
                    self._send(rid, 'report_command',
                               {'request_id': c['request_id'], 'status': doc['status'],
                                'text': self._report_text(doc)[:fabric_relay.MAX_COMMAND_REPORT]})
                except fabric_relay.RelayError:
                    pass
        return new

    def list(self):
        with self._lock:
            return [{'request_id': k, **self.pending[k]} for k in self._order if k in self.pending]


def companion_commands(server):
    if getattr(server, 'companion_commands', None) is None:
        server.companion_commands = CompanionCommands(server)
    return server.companion_commands
