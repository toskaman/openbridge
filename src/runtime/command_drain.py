"""Drain Companion command queues: get_commands -> parse/transcribe -> report_command.

The Companion queues owner-typed and owner-spoken commands on-device and shows
"Got it" until the PC reports back. Without this drain nothing ever reads the
queue, so the screen would stay on "Got it" forever. Every drained command gets
exactly one report (parse outcome, clarification, or an honest error) — the
Companion is never left hanging.

Safety: local tiers only (cloud_consent False, 'high' demoted to 'auto'), parse
outcomes are REPORTED, never auto-approved or executed from this channel.
"""
import sys
import threading
import time
import traceback

from src.fabric import relay as R
from src.runtime import command as CMD

MAX_REPORT = 150   # under the relay's MAX_COMMAND_REPORT (160)
POLL_INTERVAL_S = 5.0


def _short(text, n=MAX_REPORT):
    t = str(text or '').strip().replace('\n', ' ')
    return t if len(t) <= n else t[:n - 1] + '…'


def _outcome_text(doc):
    status = doc.get('status')
    amb = doc.get('ambiguities') or []
    if status == 'resolved':
        return doc.get('outcome') or 'Understood.'
    if status == 'needs_clarification':
        return doc.get('clarifying_question') or 'Need clarification.'
    if status == 'unsupported':
        return amb[0] if amb else 'No registered skill matches.'
    if status == 'escalation_required':
        return amb[0] if amb else 'Needs explicit authorization on your PC.'
    return 'Parse outcome unclear.'


def _parse_local(server, parse_fn, text, cmd):
    # Fast local tier only: the drain reports outcomes, it never spends medium/cloud
    # inference (medium OOMs small hosts and would stall the poll loop for minutes).
    body = {'text': text, 'lang': cmd['lang'], 'quality': 'low', 'cloud_consent': False}
    return parse_fn(server, body)['intent']


def _transcribe(pcm, lang, transcribe_fn, stt_available):
    """Return transcript text ('' when silence), or None when STT is unavailable."""
    if transcribe_fn is not None:
        return transcribe_fn(pcm, lang)
    from src.ai import stt_local
    ok = stt_local.available() if stt_available is None else stt_available
    if not ok:
        return None
    d = stt_local.transcribe_pcm(bytes(pcm), lang)
    return (d.get('transcript') or '').strip()


def _handle(server, relay, rid, cmd, parse_fn, fetch_voice_fn, transcribe_fn, stt_available):
    """Return (report_status, report_text) for one validated command."""
    parse_fn = parse_fn or CMD.parse_request
    if cmd['kind'] == 'oracle':
        from src.ai import oracle as Oracle
        ans = Oracle.oracle_answer(cmd['text'])
        Oracle.push_oracle_to_hud(server, ans, mic_source=cmd.get('mic_source') or rid)
        return ('resolved', _short(f"{ans['answer']} ({ans['latency_ms']}ms)"))
    if cmd['kind'] == 'voice':
        fetch = fetch_voice_fn or R.fetch_voice_urls
        # Identity check on the default multi-URL fetch: wrappers/partials of
        # it are not recognized and fail loudly (RelayError), never silently.
        if fetch is R.fetch_voice_urls:
            pcm = fetch(relay.get('urls') or [relay['url']], relay['key'], cmd['clip_id'],
                        cmd['bytes'], cmd['sha256'], relay_id=rid, aead_version=relay.get('aead'))
        else:  # injected doubles keep the single-URL call shape
            pcm = fetch(relay['url'], relay['key'], cmd['clip_id'], cmd['bytes'], cmd['sha256'],
                        relay_id=rid, aead_version=relay.get('aead'))
        secs = len(pcm) / 2 / 16000
        heard = _transcribe(pcm, cmd['lang'], transcribe_fn, stt_available)
        if heard is None:
            return ('escalation_required',
                    'Voice received (%.0f s) but transcription is unavailable on this PC right now.' % secs)
        if not heard:
            return ('escalation_required', 'Heard only silence — try again closer to the mic.')
        prefix = 'Heard: "%s". ' % heard[:60]
        text = heard
    else:
        prefix, text = '', cmd['text']
    layout = getattr(server, 'voice_layout', None)   # opt-in (voice_layout.enable); None in production
    if layout is not None:
        hit = layout(rid, relay, text, cmd.get('lang'))
        if hit is not None:
            return hit[0], prefix + hit[1]
    from src.glasses import watch_controls as _WC
    _from_watch = bool((relay.get('declared') or {}).get('watch') or (relay.get('declared') or {}).get('form_factor') == 'watch')
    _engo = _WC.match_engo_watch_command(text, lang_hint=cmd.get('lang'), from_watch=_from_watch)
    if _engo is not None:
        _res = _WC.apply_engo_watch_order(server, _engo, source_relay_id=rid)
        return (_res['status'], _short(prefix + _res['text']))
    if cmd['kind'] == 'oracle':
        from src.ai import oracle as Oracle
        ans = Oracle.oracle_answer(cmd['text'])
        Oracle.push_oracle_to_hud(server, ans, mic_source=cmd.get('mic_source') or rid)
        return ('resolved', _short(f"{ans['answer']} ({ans['latency_ms']}ms)"))
    if cmd['kind'] == 'voice':
        # Campaign Two §4.6: deterministic fail-closed screens for STT
        # transcripts (refusals, conflicts, presses, moves, locate). Typed
        # text is certain input and always reaches the model tier.
        from src.ai import voice_normalize as _VN
        _screen = _VN.screen_voice_transcript(text, lang_hint=cmd.get('lang'))
        if _screen is not None:
            return (_screen['status'], prefix + _screen['text'])
    try:
        doc = _parse_local(server, parse_fn, text, cmd)
    except CMD.CommandError as e:
        return 'escalation_required', prefix + 'Could not parse that (%s).' % e
    status = doc.get('status')
    if status not in ('resolved', 'needs_clarification', 'unsupported', 'escalation_required'):
        status = 'escalation_required'
    return status, prefix + _outcome_text(doc)


def _report_one(server, relay, rid, cmd, parse_fn, fetch_voice_fn, transcribe_fn,
                stt_available, stats, lock):
    try:
        status, text = _handle(server, relay, rid, cmd, parse_fn,
                               fetch_voice_fn, transcribe_fn, stt_available)
        rep = relay['send'](relay, R.command(
            relay['key'], rid, 'report_command',
            {'request_id': cmd['request_id'], 'status': status, 'text': _short(text)}))
        R.verify(relay['key'], rep, relay['seen'])
        with lock:
            stats['reported'] += 1
        sys.stderr.write('[drain] %s %s -> %s: %s\n' % (rid, cmd['request_id'][:8], status, text[:80]))
    except Exception as e:
        with lock:
            stats['errors'].append('%s/%s: %s: %s' % (rid, cmd['request_id'], type(e).__name__, e))
        sys.stderr.write('[drain] %s %s failed: %s: %s\n'
                         % (rid, cmd['request_id'][:8], type(e).__name__, e))


def poll_once(server, parse_fn=None, fetch_voice_fn=None, transcribe_fn=None,
              stt_available=None, sync=False, long_poll=False, wait_ms=3000):
    """Poll every command_submit-capable relay once. Never raises for relay errors.

    Each queued command is handled in its own daemon worker so a slow parse or a
    multi-GB transcription never stalls the poll loop (sync=True handles inline,
    for tests). At-most-once holds either way: get_commands already polled the
    command off the relay queue, and each worker reports exactly once.
    """
    stats = {'relays_polled': 0, 'commands': 0, 'reported': 0, 'errors': []}
    lock = threading.Lock()
    mgr = server.relays
    params = {'wait_ms': int(wait_ms)} if (long_poll and not sync and wait_ms > 0) else None
    for rid, relay in list(mgr.relays.items()):
        if 'command_submit' not in relay.get('capabilities', ()):
            continue
        if not relay.get('online', True):
            continue
        stats['relays_polled'] += 1
        try:
            reply = relay['send'](relay, R.command(relay['key'], rid, 'get_commands', params))
            msg = R.verify(relay['key'], reply, relay.setdefault('seen', {}))
            cmds = R.validate_commands(msg.get('params', {}))
        except Exception as e:
            stats['errors'].append('%s: %s: %s' % (rid, type(e).__name__, e))
            sys.stderr.write('[drain] %s poll failed: %s: %s\n' % (rid, type(e).__name__, e))
            continue
        for cmd in cmds:
            stats['commands'] += 1
            args = (server, relay, rid, cmd, parse_fn, fetch_voice_fn, transcribe_fn,
                    stt_available, stats, lock)
            if sync:
                _report_one(*args)
            else:
                threading.Thread(target=_report_one, args=args, name='drain-worker',
                                 daemon=True).start()
    return stats


def start(server, interval_s=POLL_INTERVAL_S, **kw):
    """Start the background drain thread (idempotent). Daemon: dies with the process."""
    if getattr(server, '_command_drain_started', False):
        return None
    server._command_drain_started = True
    use_long_poll = kw.pop('long_poll', True)

    def loop():
        while True:
            polled = 0
            try:
                st = poll_once(server, long_poll=use_long_poll, **kw)
                polled = st.get('relays_polled', 0)
            except Exception:
                traceback.print_exc()
            # When an online relay is active with long-polling, re-arm immediately (<50ms)
            # instead of waiting 5s, giving near-instant (<15ms) phone->PC wakeup.
            time.sleep(0.05 if (use_long_poll and polled > 0) else interval_s)

    t = threading.Thread(target=loop, name='command-drain', daemon=True)
    t.start()
    return t
