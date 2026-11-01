"""Adaptive Route Intelligence (Campaign Two S4.4): enumerate relay routes, fail over safely.

A route is a path ``PC -> relay -> target`` for one granted capability
(e.g. ``PC -> phone -> target``, ``PC -> TV -> target``). This module is
ADVISORY plus single-dispatch: it reads ``RelayManager`` state, never edits
relay/server code, and never mutates manager state (nonce caches aside, which
``relay.verify`` owns).

At-most-once rule (the load-bearing property): a command whose outcome is
UNCERTAIN -- bytes may have left the PC but no verified reply arrived -- is
NEVER reissued. ``failover`` of such a record raises ``UncertainOutcome``
instead of transmitting anything. Only a record classified NOT_SENT (nothing
left the PC: no route, relay down/busy pre-send, pre-send validation refusal)
may be re-dispatched, and then only as a FRESH command (new nonce) on an
alternate route. A fresh read-only probe (new nonce, e.g. ``get_status``) is
always allowed: it is reconciliation, not a reissue.
"""

import threading
from dataclasses import dataclass, field

from src.fabric import relay as R

CAPABILITY = 'ble_scan'

ACKED = 'ACKED'                     # verified reply received
NOT_SENT = 'NOT_SENT'               # nothing left the PC; safe to try an alternate route
UNCERTAIN = 'UNCERTAIN'             # may have been received; MUST never be reissued
REFUSED_KNOWN = 'REFUSED_KNOWN'     # relay received and refused; known outcome, no auto-retry

OUTCOMES = (ACKED, NOT_SENT, UNCERTAIN, REFUSED_KNOWN)


class UncertainOutcome(RuntimeError):
    """Fail-closed refusal: the original command outcome is uncertain, so no
    reissue on any route is allowed. Reconcile with a fresh probe instead."""


@dataclass(frozen=True)
class Route:
    target: str               # target device key (opaque label)
    relay_id: str             # relay carrying this route
    hops: tuple               # ('pc', relay_id, target)
    rank: int                 # 0 = most preferred


@dataclass
class DispatchRecord:
    target: str               # intended target device key (always kept, even route-less)
    route: Route | None       # None when no route existed pre-send
    command: dict | None      # envelope sent (or built); None when unbuildable
    outcome: str              # one of OUTCOMES
    reply: dict | None = None
    error: str | None = None


@dataclass
class LossSimulation:
    target: str
    lost: Route | None            # preferred route before the loss (may be None)
    alternate: Route | None       # best surviving route (may be None)
    remaining: list = field(default_factory=list)


def _check_target(target):
    if not isinstance(target, str) or not target.strip():
        raise ValueError('target must be a non-empty device key')
    return target.strip()


class RouteIntel:
    """Enumerate routes over a RelayManager and dispatch at-most-once."""

    def __init__(self, manager):
        self.manager = manager
        self.uncertain = set()        # nonces of commands whose outcome is uncertain
        self._lock = threading.Lock()

    # -- enumeration ----------------------------------------------------

    def routes_for(self, target, capability=CAPABILITY, down=()):
        """All currently valid routes for target, best first.

        Valid = relay is eligible in the manager (granted capability +
        permission + owner consent + online + not busy) and not in `down`.
        `down` is a simulated disappearance set: pure, touches no manager state.
        """
        target = _check_target(target)
        down = set(down or ())
        routes = []
        for rank, rid in enumerate(self.manager.eligible(capability)):
            if rid in down:
                continue
            routes.append(Route(target=target, relay_id=rid,
                                hops=('pc', rid, target), rank=rank))
        # Re-rank after filtering so ranks stay dense.
        return [Route(target=r.target, relay_id=r.relay_id, hops=r.hops, rank=i)
                for i, r in enumerate(routes)]

    def select(self, target, capability=CAPABILITY, down=(), exclude=()):
        """Best route for target, or None when no valid route exists."""
        routes = [r for r in self.routes_for(target, capability, down)
                  if r.relay_id not in set(exclude or ())]
        return routes[0] if routes else None

    def simulate_loss(self, target, lost_relay, capability=CAPABILITY, down=()):
        """Simulate the disappearance of `lost_relay`: what was preferred, what
        survives. Pure: no manager state is touched."""
        target = _check_target(target)
        before = self.routes_for(target, capability, down)
        lost = next((r for r in before if r.relay_id == lost_relay), None)
        remaining = self.routes_for(target, capability, set(down or ()) | {lost_relay})
        return LossSimulation(target=target, lost=lost,
                              alternate=remaining[0] if remaining else None,
                              remaining=remaining)

    # -- at-most-once ledger --------------------------------------------

    def reissue_allowed(self, command):
        """False when `command` is a quarantined uncertain envelope."""
        return isinstance(command, dict) and command.get('nonce') not in self.uncertain

    def assert_fresh(self, command):
        """Raise UncertainOutcome if `command` was quarantined as uncertain."""
        if not self.reissue_allowed(command):
            raise UncertainOutcome(
                'Command outcome is uncertain; it must never be reissued '
                '(reconcile with a fresh probe instead)')

    def _quarantine(self, nonce):
        with self._lock:
            self.uncertain.add(nonce)

    # -- dispatch --------------------------------------------------------

    def dispatch(self, target, op, params=None, capability=CAPABILITY, down=(),
                 relay_id=None):
        """Build ONE command envelope and send it at most once.

        Returns a DispatchRecord classified as ACKED / NOT_SENT / UNCERTAIN /
        REFUSED_KNOWN. Anything that happens after bytes may have left
        (transport error, bad/unverifiable reply) quarantines the nonce as
        UNCERTAIN. Pre-send failures (no route, relay down/busy, bad envelope)
        are NOT_SENT: nothing was transmitted.
        """
        target = _check_target(target)
        down = set(down or ())
        route = None
        if relay_id is not None:
            if relay_id in self.manager.eligible(capability) and relay_id not in down:
                route = Route(target=target, relay_id=relay_id,
                              hops=('pc', relay_id, target), rank=0)
            else:
                # Pre-send refusal: build the envelope when the key is known so
                # the record keeps op/params for failover, but transmit nothing.
                entry = self.manager.relays.get(relay_id)
                cmd = None
                if entry is not None and 'key' in entry:
                    try:
                        cmd = R.command(entry['key'], relay_id, op, params)
                    except R.RelayError:
                        cmd = None
                return DispatchRecord(target, None, cmd, NOT_SENT, error=
                                      'Relay %r has no valid route (missing permission, '
                                      'offline, busy or simulated down)' % (relay_id,))
        else:
            route = self.select(target, capability, down)
            if route is None:
                return DispatchRecord(target, None, None, NOT_SENT, error=
                                      'No authorized route to %r' % (target,))
        entry = self.manager.relays.get(route.relay_id)
        if entry is None or not entry.get('online') or entry.get('busy'):
            return DispatchRecord(target, route, None, NOT_SENT, error=
                                  'Relay %r became unavailable before dispatch'
                                  % (route.relay_id,))
        try:
            cmd = R.command(entry['key'], route.relay_id, op, params)
        except R.RelayError as error:
            return DispatchRecord(target, route, None, NOT_SENT, error=str(error))
        self.assert_fresh(cmd)      # defense in depth: a quarantined nonce never goes out
        try:
            reply = self.manager.transport(entry, cmd)
        except R.RelayError as error:
            # Protocol refusal from the relay itself: it received the command
            # and said no. Known outcome -- no auto-retry, no quarantine.
            return DispatchRecord(target, route, cmd, REFUSED_KNOWN, error=str(error))
        except (OSError, TimeoutError) as error:
            # Bytes may have left; the reply never arrived. Uncertain forever.
            self._quarantine(cmd['nonce'])
            return DispatchRecord(target, route, cmd, UNCERTAIN, error=
                                  '%s during dispatch (outcome uncertain; must not reissue)'
                                  % type(error).__name__)
        try:
            msg = R.verify(entry['key'], reply, entry['seen'])
        except (R.RelayError, TypeError, ValueError) as error:
            # The relay got the command (it answered something) but the reply
            # is unverifiable: the effect is unknown. Uncertain forever.
            self._quarantine(cmd['nonce'])
            return DispatchRecord(target, route, cmd, UNCERTAIN, error=
                                  'Unverifiable reply (outcome uncertain; must not reissue): %s'
                                  % error)
        return DispatchRecord(target, route, cmd, ACKED, reply=msg.get('params', {}))

    def failover(self, record, target=None, capability=CAPABILITY, down=()):
        """Re-dispatch ONLY a NOT_SENT record on an alternate route.

        The retry is a FRESH command (new nonce), never the original envelope.
        UNCERTAIN records raise UncertainOutcome and transmit nothing;
        ACKED/REFUSED_KNOWN records raise ValueError (nothing to fail over).
        """
        if record.outcome == UNCERTAIN:
            raise UncertainOutcome(
                'Original outcome is uncertain; the command must never be '
                'reissued on any route (reconcile with a fresh probe instead)')
        if record.outcome != NOT_SENT:
            raise ValueError('Only a NOT_SENT record can fail over (got %s)'
                             % record.outcome)
        target = _check_target(target or record.target)
        op = (record.command or {}).get('op', 'get_status')
        params = dict((record.command or {}).get('params', {}))
        exclude = [record.route.relay_id] if record.route else []
        route = self.select(target, capability, down, exclude=exclude)
        if route is None:
            return DispatchRecord(target, None, None, NOT_SENT, error=
                                  'No surviving alternate route to %r' % (target,))
        return self.dispatch(target, op, params, capability, down,
                             relay_id=route.relay_id)
