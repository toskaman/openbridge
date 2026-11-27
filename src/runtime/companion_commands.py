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
        self.listeners = []  # fn(relay_id, text, intent): e.g. the glasses hub showing and running voice commands

    def _send(self, rid, op, params=None):
        r = self.server.relays.relays[rid]
        msg = fabric_relay.command(r['key'], rid, op, params)
        try:
            return fabric_relay.verify(r['key'], r['send'](r, msg), r['seen']).get('params', {})
        except (OSError, TimeoutError):
            r['online'] = False
            raise fabric_relay.RelayError('Relay unreachable') from None

    def _voice_text(self, rid, relay, item):
        """Download + locally transcribe a voice clip. Returns the transcript, or None
        after reporting the failure back to the device (which then drops the clip)."""
        from src.ai import stt_local, voice_stt
        reason = None
        if not relay.get('url'):
            reason = 'Voice needs a fresh pairing — pair this device again'
        elif not stt_local.available():
            reason = 'Voice model not installed on this PC — type instead'
        else:
            try:
                pcm = fabric_relay.fetch_voice_urls(relay.get('urls') or [relay['url']], relay['key'],
                                                      item['clip_id'], item['bytes'], item['sha256'],
                                                      relay_id=rid, aead_version=relay.get('aead'))
                doc = stt_local.transcribe_pcm(pcm, item['lang'])
                heard = ' '.join(str(doc.get('transcript', '')).split())
                if heard:
                    return heard
                reason = 'Did not catch that — try again or type'
            except voice_stt.STTBlocked as blocked:
                reason = str(blocked)      # worker crash/timeout/low-RAM: report it, not a download failure
            except (fabric_relay.RelayError, OSError):
                reason = 'Voice download failed — try again or type'
        try:
            self._send(rid, 'report_command',
                       {'request_id': item['request_id'], 'status': 'escalation_required',
                        'text': reason[:fabric_relay.MAX_COMMAND_REPORT]})
        except fabric_relay.RelayError:
            pass
        return None

    def _vision(self, rid, relay, item):
        """Visual Oracle: download the phone's photo like a voice clip (signed, size + sha256 checked, encrypted after
        aead1), answer with a local vision model, show it on the glasses, report it to the phone. The photo is
        only kept in memory for this call."""
        from src.ai import oracle as Oracle
        try:
            jpeg = fabric_relay.fetch_voice_urls(relay.get('urls') or [relay['url']], relay['key'], item['clip_id'],
                                                 item['bytes'], item['sha256'], relay_id=rid, aead_version=relay.get('aead'))
        except (fabric_relay.RelayError, OSError, KeyError):
            jpeg = None
        if not jpeg or not jpeg.startswith(b'\xff\xd8'):
            text, status = 'Photo download failed — try again', 'escalation_required'
        else:
            ans = Oracle.vision_answer(jpeg, item.get('text', ''), item.get('lang', 'fr'))
            Oracle.push_oracle_to_hud(self.server, ans, mic_source='phone_camera')
            text, status = '%s (%sms)' % (ans['answer'], ans['latency_ms']), 'resolved'
            for fn in list(self.listeners):
                try:
                    fn(rid, ans['transcript'], {'status': 'resolved', 'skill_id': 'voice.oracle', 'oracle': ans})
                except Exception:  # noqa: BLE001 - a listener never breaks the command path
                    pass
        try:
            self._send(rid, 'report_command', {'request_id': item['request_id'], 'status': status,
                                               'text': text[:fabric_relay.MAX_COMMAND_REPORT]})
        except fabric_relay.RelayError:
            pass

    def _report_text(self, doc):
        st = doc['status']
        if st == 'resolved':
            return f"{doc['skill_id']} ready — review on this PC"
        if st == 'needs_clarification':
            return str(doc.get('clarifying_question') or 'Clarification needed')
        amb = (doc.get('ambiguities') or ['no detail'])
        return f"{'Unsupported' if st == 'unsupported' else 'Escalation needed'}: {amb[0]}"

    NAV_WORDS = {'suivant': 'next', 'next': 'next', 'ouvre': 'ok', 'ouvrir': 'ok', 'open': 'ok', 'ok': 'ok',
                 'valide': 'ok', 'retour': 'back', 'back': 'back', 'reviens': 'back', 'accueil': 'home',
                 'home': 'home', 'menu': 'home'}

    def _glasses_nav(self, rid, c, said):
        """'suivant', 'ouvre', 'retour', 'accueil' said alone on a Companion drive the glasses menus (only when a
        glasses hub runs; a longer order such as 'ouvre YouTube' is never taken as navigation)."""
        hub = getattr(self.server, 'glasses_hub', None)
        import unicodedata
        words = ''.join(ch for ch in unicodedata.normalize('NFKD', str(said or '').lower())
                        if not unicodedata.combining(ch)).strip(' .!?').split()
        if hub is None or len(words) != 1 or words[0] not in self.NAV_WORDS:
            return False
        hub.press(self.NAV_WORDS[words[0]])
        try:
            self._send(rid, 'report_command', {'request_id': c['request_id'], 'status': 'resolved',
                                               'text': 'Glasses: ' + self.NAV_WORDS[words[0]]})
        except fabric_relay.RelayError:
            pass
        return True

    def _module_toggle(self, rid, c, said):
        """'désactive l'Oracle' typed or spoken on a Companion: switch the module on that device and say so."""
        from src.runtime import companion_modules as M
        print('[companion] %s %s: %r' % (rid, c.get('kind'), said), flush=True)   # what the PC understood
        t = M.parse_toggle(said)
        if t is None:
            return False
        module, on = t
        fr = c.get('lang') == 'fr'
        try:
            M.set_module(self.server, rid, module, on)
            msg = ('Oracle activé' if on else 'Oracle désactivé') if fr else ('Oracle turned on' if on else 'Oracle turned off')
            status = 'resolved'
        except (fabric_relay.RelayError, ValueError) as e:
            msg, status = str(e)[:fabric_relay.MAX_COMMAND_REPORT], 'escalation_required'
        try:
            self._send(rid, 'report_command', {'request_id': c['request_id'], 'status': status, 'text': msg})
        except fabric_relay.RelayError:
            pass
        return True

    def _engo_watch_order(self, rid, relay, c, said):
        from src.glasses import watch_controls as WC
        from_watch = bool((relay.get('declared') or {}).get('watch') or (relay.get('declared') or {}).get('form_factor') == 'watch')
        order = WC.match_engo_watch_command(said, lang_hint=c.get('lang'), from_watch=from_watch)
        if order is None:
            return False
        res = WC.apply_engo_watch_order(self.server, order, source_relay_id=rid)
        try:
            self._send(rid, 'report_command', {
                'request_id': c['request_id'],
                'status': res['status'],
                'text': res['text'][:fabric_relay.MAX_COMMAND_REPORT],
            })
        except fabric_relay.RelayError:
            pass
        return True

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
                text = c.get('text', '')
                if c.get('kind') in ('text', 'voice') and c.get('mode') != 'oracle':
                    said = text if c.get('kind') == 'text' else self._voice_text(rid, r, c)
                    if said is None:
                        continue
                    if self._module_toggle(rid, c, said):
                        continue
                    if self._glasses_nav(rid, c, said):
                        continue
                    if self._engo_watch_order(rid, r, c, said):
                        continue
                    if c.get('kind') == 'voice':
                        c = dict(c, kind='text', text=said)
                        text = said
                if c.get('kind') == 'vision':
                    self._vision(rid, r, c)
                    new += 1
                    continue
                if c.get('kind') == 'voice' and c.get('mode') == 'oracle':
                    text = self._voice_text(rid, r, c)
                    if text is None:
                        continue
                    c = dict(c, kind='oracle', text=text, mic_source='phone_mic_pc_stt')
                if c.get('kind') == 'oracle':
                    from src.ai import oracle as Oracle
                    ans = Oracle.oracle_answer(text)
                    Oracle.push_oracle_to_hud(self.server, ans, mic_source=c.get('mic_source') or rid)
                    doc = {'status': 'resolved', 'skill_id': 'voice.oracle', 'oracle': ans}
                    with self._lock:
                        self.pending[c['request_id']] = {'relay_id': rid, 'text': text,
                                                         'lang': c['lang'], 'intent': doc}
                        self._order.append(c['request_id'])
                        while len(self._order) > MAX_PENDING:
                            self.pending.pop(self._order.pop(0), None)
                    new += 1
                    for fn in list(self.listeners):
                        try:
                            fn(rid, text, doc)
                        except Exception:
                            pass
                    try:
                        self._send(rid, 'report_command',
                                   {'request_id': c['request_id'], 'status': 'resolved',
                                    'text': f"{ans['answer']} ({ans['latency_ms']}ms)"[:fabric_relay.MAX_COMMAND_REPORT]})
                    except fabric_relay.RelayError:
                        pass
                    continue
                if c.get('kind') == 'voice':
                    # Device-side voice: download the clip, transcribe with local Meta STT,
                    # then parse exactly like typed text. Sound stays on the device; only
                    # the transcript flows through the existing parse path.
                    text = self._voice_text(rid, r, c)
                    if text is None:
                        continue
                quality = c['quality'] if c['quality'] in ('low', 'medium') else 'auto'
                doc = N.parse(text, c['lang'], quality, low, None, medium,
                              cloud_allowed=False)
                with self._lock:
                    self.pending[c['request_id']] = {'relay_id': rid, 'text': text,
                                                     'lang': c['lang'], 'intent': doc}
                    self._order.append(c['request_id'])
                    while len(self._order) > MAX_PENDING:
                        self.pending.pop(self._order.pop(0), None)
                new += 1
                for fn in list(self.listeners):
                    try:
                        fn(rid, text, doc)
                    except Exception:  # noqa: BLE001 - a listener never breaks the command path
                        pass
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
