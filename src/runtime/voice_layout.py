"""Owner voice -> watch button LAYOUT (create / remove menus). Opt-in, off by default.

Creation is decided by the pinned LOCAL Meta model (llama3.2 3B, nl_router low tier):
the transcript goes through the same prompt / schema / validator as
`openbridge dashboards propose` (value-free device bundle, opaque ids, bindable
skills only). Meta may answer proposal / clarification / refusal; only a validated
proposal whose target is an id actually offered is installed, through the same
dashboards.install_patch -> set_controls path as the CLI. Removal is a fixed,
deterministic revoke (set_controls([])) -- the safe direction needs no model.
Voice never presses and never executes a skill: a created button still needs one
physical tap on the watch, which goes through normal RemoteControls dispatch
(lease, TTL, burst, grant generation, exactly-once journal).

Who may do it: only the paired relay the order came from (signed command_submit),
only when that relay also declares remote_controls, only after the owner enabled
the layer for this server (enable()). Production servers never call enable(), so
the drain stays reports-only there.

Ambiguity fails closed: both create and remove words -> a clarification report, no
model call, no layout change. Meta clarification/refusal/invalid JSON -> reported,
nothing installed.
"""
import hashlib
import json
import re
import time
from pathlib import Path

from src.ai import voice_normalize as VN

_CREATE_RX = re.compile(
    r'\b(mets?|mas|mais|mettre|mettez|ajoute\w*|cree\w*|creer|affiche\w*|installe\w*|'
    r'donne\w*|add|create|put|show|install|give)\b')
_REMOVE_RX = re.compile(
    r'\b(enleve\w*|enlever|retire\w*|supprime\w*|efface\w*|vire\w*|cache\w*|'
    r'remove\w*|delete\w*|hide\w*|clear\w*)\b')
_OBJECT_RX = re.compile(
    r'\b(bou?tt?ons?|menus?|commandes?|controles?|telecommandes?|touches?|'
    r'butt?ons?|controls?|remotes?)\b')

TEXT = {
    'created_meta': {'fr': 'Meta a créé : %s. Appuie pour essayer.',
                     'en': 'Meta created: %s. Tap to try.'},
    'meta_no': {'fr': 'Meta n\'a rien créé : %s', 'en': 'Meta created nothing: %s'},
    'removed': {'fr': 'Boutons retirés de la montre.',
                'en': 'Buttons removed from the watch.'},
    'both': {'fr': 'Créer ou enlever ? Dis une seule chose à la fois.',
             'en': 'Create or remove? Say one thing at a time.'},
    'no_tv': {'fr': 'Meta a visé un appareil non proposé, aucun bouton créé.',
              'en': 'Meta targeted a device that was not offered, no button created.'},
    'no_caps': {'fr': 'Cette montre ne peut pas recevoir de boutons.',
                'en': 'This watch cannot receive buttons.'},
    'failed': {'fr': 'Changement de boutons refusé : %s',
               'en': 'Button change refused: %s'},
}


def _t(key, lang):
    return TEXT[key]['fr' if lang == 'fr' else 'en']


def match(transcript, lang_hint=None):
    """-> None (not a layout order) or {'op': create|remove|clarify, 'why'?, 'lang'}."""
    norm = VN.normalize(transcript, lang_hint)
    fixed, lang = norm['fixed'], norm['lang']
    if not fixed or not _OBJECT_RX.search(fixed):
        return None
    create, remove = bool(_CREATE_RX.search(fixed)), bool(_REMOVE_RX.search(fixed))
    if create and remove:
        return {'op': 'clarify', 'why': 'both', 'lang': lang}
    if remove:
        return {'op': 'remove', 'lang': lang}
    if create:
        return {'op': 'create', 'lang': lang}
    return None


def resolve_tv_key(server):
    """Exactly one TV in the graph, else None (prefer the one with a companion relay service)."""
    devs = [d for d in ((server.fabric_snapshot or {}).get('devices') or []) if d.get('category') == 'tv']
    if len(devs) > 1:
        def companion(d):
            svcs = (((d.get('facts') or {}).get('mdns_services') or {}).get('value')) or []
            caps = [(c or {}).get('name') for c in d.get('capabilities') or []]
            return '_openbridge-relay._tcp' in svcs or 'companion_relay' in caps
        devs = [d for d in devs if companion(d)]
    return devs[0]['key'] if len(devs) == 1 else None


# Voice panels are living-room remotes for the speaking watch: Meta designs among
# these primitives for these devices only (the ADB-attached TV, the linked vacuum).
# Narrow offers keep a 3B CPU model accurate; the strict validator still decides.
# tv_volume_set / tv_sleep are left out: the 3B model kept binding "Volume up" to an
# absolute set and adding unasked "TV sleep" buttons (meta-runs evidence, 02-Nov 18:27).
SCOPE_PRIMITIVES = ('tv_volume_step', 'tv_wake', 'app_launch', 'vacuum_command')
# app_launch is offered for the TV with an allowlisted package only (enum below).
TV_APPS = {'com.google.android.youtube.tv': 'youtube'}
MAX_ATTEMPTS = 2   # one self-correction: the validator's error is fed back verbatim


VOICE_RULES = ('\nVoice panel rules: add ONLY the buttons the request asks for (2 buttons when it asks for '
               'volume buttons). Label each button with what its primitive really does, in the language of the '
               'request (e.g. tv_volume_step up = "Volume +"); never label a button with an effect its primitive '
               'does not have. Leave reason, code and clarifying_question out of a proposal.')


PARAM_SCHEMAS = {
    'tv_volume_step': {'type': 'object', 'required': ['direction'],
                       'properties': {'direction': {'type': 'string', 'enum': ['up', 'down']}}},
    'tv_volume_set': {'type': 'object', 'required': ['value'],
                      'properties': {'value': {'type': 'integer', 'minimum': 0, 'maximum': 100}}},
    'tv_wake': {'type': 'object', 'properties': {}},
    'app_launch': {'type': 'object', 'required': ['package'],
                   'properties': {'package': {'type': 'string', 'enum': sorted(TV_APPS)}}},
    'tv_sleep': {'type': 'object', 'properties': {}},
    'vacuum_command': {'type': 'object', 'required': ['command'],
                       'properties': {'command': {'type': 'string', 'enum': ['start', 'pause', 'dock', 'seek']}}},
}


def response_schema(offered_ids, bindable):
    """Constrained-decoding schema for this request: offered ids, primitives and their typed
    params as enums/anyOf. Decoding constraints only narrow what the model can emit;
    v4_ui, label_check and set_controls still validate."""
    variants = [{'type': 'object', 'required': ['widget_id', 'kind', 'label', 'binding_primitive', 'params'],
                 'properties': {'widget_id': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['button']},
                                'label': {'type': 'string'},
                                'binding_primitive': {'type': 'string', 'enum': [p]},
                                'params': PARAM_SCHEMAS.get(p, {'type': 'object'})}}
                for p in bindable]
    patch = {'type': 'object',
             'required': ['schema_version', 'patch_id', 'target_opaque_id', 'origin', 'model_run_id', 'widgets'],
             'properties': {'schema_version': {'type': 'integer'}, 'patch_id': {'type': 'string'},
                            'target_opaque_id': {'type': 'string', 'enum': list(offered_ids)},
                            'origin': {'type': 'string', 'enum': ['meta_generated']},
                            'model_run_id': {'type': 'string'},
                            'widgets': {'type': 'array', 'items': {'anyOf': variants}}}}
    return {'type': 'object', 'required': ['outcome'],
            'properties': {'outcome': {'type': 'string', 'enum': ['proposal', 'refusal', 'clarification']},
                           'patch': patch, 'reason': {'type': 'string'},
                           'clarifying_question': {'type': 'string'}}}


PRIMITIVE_CATEGORY = {'app_launch': 'tv', 'tv_volume_step': 'tv', 'tv_wake': 'tv', 'tv_volume_set': 'tv', 'tv_sleep': 'tv',
                      'vacuum_command': 'vacuum'}


def target_check(widgets, category):
    """Every button must act on the patch's single target: tv_* on the TV, vacuum_command on the vacuum."""
    for w in widgets:
        want = PRIMITIVE_CATEGORY.get(w.get('binding_primitive'))
        if want and want != category:
            return ('TARGET_MISMATCH: "%s" uses %s (a %s primitive) but the patch targets a %s; one panel = one '
                    'device, use only that device\'s primitives' % (w.get('label'), w.get('binding_primitive'), want, category))
    return None


_UP_RX = re.compile(r'(\+|\bup\b|\bplus\b|\bmonte\w*|\bhaut\b|\blouder\b|\bincrease\b|\baugment\w*)', re.I)
_DOWN_RX = re.compile(r'(\B-\B|-$|\s-\s|\bdown\b|\bmoins\b|\bbaisse\w*|\bbas\b|\bquieter\b|\bdecrease\b|\bdiminu\w*)', re.I)
_MUTE_RX = re.compile(r'\b(mute|muet|sourdine|silence)\b', re.I)


def label_check(widgets):
    """A button must not lie: a volume-up/down/mute label must match what its binding does.

    -> None when coherent, else 'LABEL_MISMATCH: ...' (fed back to Meta, never installed)."""
    for w in widgets:
        lab, prim, prm = w.get('label', ''), w.get('binding_primitive'), w.get('params') or {}
        if prim == 'app_launch':
            app = TV_APPS.get(prm.get('package'))
            if app is None:
                return 'LABEL_MISMATCH: app_launch package %r is not allowlisted' % prm.get('package')
            if app not in lab.lower():
                return 'LABEL_MISMATCH: "%s" launches %s; the label must name it' % (lab, app)
            continue
        if _MUTE_RX.search(lab):
            return 'LABEL_MISMATCH: "%s" -- no mute primitive is offered' % lab
        up, down = bool(_UP_RX.search(lab)), bool(_DOWN_RX.search(lab))
        if up and down:
            return 'LABEL_MISMATCH: "%s" says both up and down' % lab
        if up or down:
            want = 'up' if up else 'down'
            if prim != 'tv_volume_step' or prm.get('direction') != want:
                return ('LABEL_MISMATCH: "%s" must bind tv_volume_step {"direction": "%s"}, got %s %s'
                        % (lab, want, prim, json.dumps(prm)))
    return None


def drop_empty_envelope(doc):
    """Normalize grammar-decoder envelope noise before the strict parse (raw reply is kept as evidence).

    A proposal carries no reason/code/clarifying_question (meta_result rejects them), so
    they are dropped from a proposal; elsewhere only empty-string optional keys are dropped."""
    if not isinstance(doc, dict):
        return doc
    opt = ('reason', 'code', 'clarifying_question')
    if doc.get('outcome') == 'proposal':
        return {k: v for k, v in doc.items() if k not in opt}
    return {k: v for k, v in doc.items() if not (k in opt and v in ('', None))}


_VAC_WORDS = re.compile(r'\b(aspirateur\w*|aspi|robot\w*|vacuum\w*|menage)\b')
_TV_WORDS = re.compile(r'\b(tele\w*|tv|televiseur|volume\w*|son|sound|youtube|yutube|you tube)\b')


def scoped_devices(server, text=''):
    """The ADB-attached TV and the linked vacuum; when the request names exactly one of
    them, only that one is offered (a 3B model otherwise mixes targets)."""
    devs = list((server.fabric_snapshot or {}).get('devices') or [])
    tv = [d for d in devs if d.get('key') == resolve_tv_key(server)]
    vac = [d for d in devs if d.get('category') == 'vacuum']
    vac = vac[:1] if len(vac) == 1 else []
    fixed = VN.normalize(text)['fixed'] if text else ''
    wants_vac, wants_tv = bool(_VAC_WORDS.search(fixed)), bool(_TV_WORDS.search(fixed))
    if wants_vac and not wants_tv:
        return vac
    if wants_tv and not wants_vac:
        return tv
    return tv + vac


def meta_propose(server, text, transport=None, evidence_dir=None):
    """Ask the pinned local Meta model to draft a watch panel for `text` (live graph).

    -> dict(outcome, patch?, detail, target_key?, attempts, model_run, elapsed_s). Raises on
    transport failure (caller reports it honestly)."""
    from src.cli import build_bundle, extract_json
    from src.forge import v4_ui, v4_uidraft
    from src.runtime import nl_plan, nl_router
    from src.runtime.dashboards import BINDABLE_PATCH_SKILLS
    from src.runtime.routing import SKILLS
    model_id, endpoint = nl_router.TIERS['low']
    devices = scoped_devices(server, text)
    cats = {d.get('category') for d in devices}
    bindable = tuple(p for p in SCOPE_PRIMITIVES if p in BINDABLE_PATCH_SKILLS and PRIMITIVE_CATEGORY.get(p) in cats)
    bundle = build_bundle(devices, list(bindable), salt='voice-%d' % int(time.time()))
    prompt_devices = [{'label': row.get('label', '?'), 'category': b['category'], 'opaque_id': b['opaque_id']}
                      for row, b in zip(devices, bundle['devices'])]
    opaque_to_key = {b['opaque_id']: row.get('key') for row, b in zip(devices, bundle['devices'])}
    hints = {sid: nl_plan.param_hint(SKILLS[sid].get('input')) for sid in bindable if sid in SKILLS}
    base_prompt = v4_uidraft.build_ui_prompt(text, prompt_devices, bindable, hints=hints) + VOICE_RULES
    if transport is None:
        fmt = response_schema([d['opaque_id'] for d in prompt_devices], bindable)
        transport = nl_plan.local_chat(model_id, endpoint, timeout=300, format=fmt,
                                       options={'num_ctx': 4096, 'num_predict': 700})
    out = {'devices': prompt_devices, 'primitives': list(bindable), 'attempts': []}
    t0 = time.time()
    prompt = base_prompt
    for attempt in range(1, MAX_ATTEMPTS + 1):
        res = transport(prompt)
        reply = res.get('content', '') if isinstance(res, dict) else res
        run = {'model_id': model_id, 'endpoint': endpoint, 'attempt': attempt,
               'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'reply_sha256': hashlib.sha256(reply.encode()).hexdigest()}
        try:
            doc, _ = extract_json(reply)
            outcome, patch, detail, code = v4_ui.parse_response_full(drop_empty_envelope(doc), bindable)
            err = None
        except (ValueError, v4_ui.UIError) as e:
            outcome, patch, detail, code, err = 'rejected', None, str(e)[:120], None, str(e)[:120]
        out['attempts'].append({'run': run, 'reply': reply, 'outcome': outcome, 'error': err})
        cat = next((d['category'] for d in prompt_devices if d['opaque_id'] == (patch or {}).get('target_opaque_id')), None)
        if outcome == 'proposal' and cat and target_check(patch['widgets'], cat):
            err = detail = target_check(patch['widgets'], cat)
            outcome, patch = 'rejected', None
            out['attempts'][-1].update(outcome=outcome, error=err)
        elif outcome == 'proposal' and label_check(patch['widgets']):
            err = detail = label_check(patch['widgets'])
            outcome, patch = 'rejected', None
            out['attempts'][-1].update(outcome=outcome, error=err)
        elif outcome == 'proposal' and opaque_to_key.get(patch.get('target_opaque_id')) is None:
            outcome, patch, err = 'rejected', None, 'TARGET_NOT_OFFERED: %s' % patch.get('target_opaque_id')
            detail = err
            out['attempts'][-1].update(outcome=outcome, error=err)
        if err is None:
            break
        prompt = (base_prompt + '\n\nYour previous reply was REJECTED by the validator with: %s. '
                  'Reply again with exactly the documented shape: inside "patch" only the keys schema_version, '
                  'patch_id, target_opaque_id, origin, model_run_id, widgets; only the listed primitives with '
                  'their exact params; each label must say what its primitive really does; target_opaque_id copied from '
                  'the Devices list.' % err)
    out.update(outcome=outcome, patch=patch, detail=detail, code=code, model_run=run,
               elapsed_s=round(time.time() - t0, 1))
    if outcome == 'proposal':
        out['target_key'] = opaque_to_key.get(patch.get('target_opaque_id'))
        out['target_label'] = next((d['label'] for d in prompt_devices
                                    if d['opaque_id'] == patch.get('target_opaque_id')), None)
    if evidence_dir:
        try:
            d = Path(evidence_dir)
            d.mkdir(parents=True, exist_ok=True)
            ev = dict(out, transcript=text, prompt=base_prompt, at=time.time())
            (d / ('meta-%d-%s.json' % (int(t0), run['reply_sha256'][:8]))).write_text(
                json.dumps(ev, indent=1, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass
    return out


def apply(server, rid, relay, m, log=None, transport=None, evidence_dir=None):
    """Apply one matched order. -> (report_status, text). Never raises."""
    from src.runtime import dashboards as D
    from src.runtime.api_v2 import remote_controls
    from src.runtime.remote_controls import RemoteControlError
    lang = m.get('lang')
    say = log or (lambda _m: None)
    if m['op'] == 'clarify':
        return 'needs_clarification', _t(m['why'], lang)
    if 'remote_controls' not in (relay.get('capabilities') or ()):
        return 'unsupported', _t('no_caps', lang)
    rc = remote_controls(server)
    try:
        if m['op'] == 'remove':
            rc.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
            say('[voice-layout] %s remove -> all buttons revoked (deterministic, no model)' % rid)
            return 'resolved', _t('removed', lang)
        say('[meta] thinking: %s (%s) drafting a watch panel...' % ('llama3.2:3b local', 'CPU'))
        r = meta_propose(server, m['text'], transport=transport, evidence_dir=evidence_dir)
        for a in r['attempts']:
            say('[meta] attempt %d: %s%s' % (a['run']['attempt'], a['outcome'],
                                             (' (%s -> retry with validator feedback)' % a['error']) if a['error'] and a is not r['attempts'][-1] else ''))
        say('[meta] %s in %.1fs reply=%s' % (r['outcome'], r['elapsed_s'], r['model_run']['reply_sha256'][:12]))
        if r['outcome'] != 'proposal':
            if r['outcome'] == 'clarification':
                return 'needs_clarification', r.get('detail') or _t('both', lang)
            return 'unsupported', (_t('meta_no', lang) % (r.get('detail') or r['outcome']))[:140]
        widgets = r['patch']['widgets']
        for w in widgets:
            say('[meta]   widget %-14s -> %s %s on %s' % (w['label'], w['binding_primitive'],
                                                        json.dumps(w['params']), r.get('target_label')))
        from src.runtime.api_v2 import router
        D.install_patch(rc, rid, r['patch'], r['target_key'], D.BINDABLE_PATCH_SKILLS,
                        consent=True, resolve_target=router(server).resolve_target)
        labels = ', '.join(w['label'] for w in widgets)[:90]
        say('[voice-layout] %s installed %d Meta button(s): %s' % (rid, len(widgets), labels))
        return 'resolved', _t('created_meta', lang) % labels
    except (RemoteControlError, D.DashboardError) as e:
        return 'escalation_required', _t('failed', lang) % str(e)[:80]
    except Exception as e:  # noqa: BLE001 - the drain must always report
        say('[voice-layout] failed %s: %s' % (type(e).__name__, str(e)[:120]))
        return 'escalation_required', _t('failed', lang) % type(e).__name__


def enable(server, log=None, transport=None, evidence_dir=None):
    """Opt this server in: the drain consults voice layout orders before parsing."""
    def hook(rid, relay, text, lang_hint=None):
        m = match(text, lang_hint)
        if m is None:
            return None
        m['text'] = text
        if log:
            log('[voice] order heard: "%s" -> %s' % (text[:80], m['op']))
        return apply(server, rid, relay, m, log=log, transport=transport, evidence_dir=evidence_dir)
    server.voice_layout = hook
    return hook
