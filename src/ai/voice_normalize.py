"""Deterministic FR/EN transcript normalization for the voice flow (Campaign Two §4.6).

Local STT (MMS-1B on watch-mic audio) mishears predictable things: "mets" ->
"mas"/"mais", "télé" -> "tellée" (see docs/evidence/voice-watch-direct-01nov.md).
This module repairs the *single-reading* errors for matching, detects the
*ambiguous* ones, and screens voice transcripts for shapes that must never
become commands: irreversible actions, conflicting intents, control presses,
control-surface moves, volume changes and locate-my-device requests.

Safety contract (tested by tests/voice/):
- Everything here is pure and deterministic: no model, no network, no clock.
- Repairs feed MATCHING only. The original transcript is always preserved for
  display and audit. A proposal may never rest on a repaired token (the
  two-pass rule in voice_intent.compile_intent: a clean match takes the
  proposal path, a repaired-only match takes clarification).
- Every screen returns None (no hit) or a clarification/refusal payload.
  Screens never return a command, a skill id or a device key.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Folding
# ---------------------------------------------------------------------------

_APOS = {'\u2019', '\u2018', '`', '\u00b4'}


def fold(text):
    """Lowercase, strip accents, split elisions/punctuation into spaces."""
    if not isinstance(text, str):
        return ''
    t = unicodedata.normalize('NFKD', text.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    for a in _APOS:
        t = t.replace(a, "'")
    t = t.replace("'", ' ')
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def tokens(folded):
    return folded.split() if folded else []


# ---------------------------------------------------------------------------
# Language detection (function-word scoring; loanwords carry no signal)
# ---------------------------------------------------------------------------

_FR = frozenset('''le la les des du de un une et est sont que qui quoi dont
dans sur pour pas mais mon ma mes ton ta sa notre votre vos nos leur leurs
aux au ce cette ces celui je tu il elle on nous vous ils elles y en
fais fait faire font trouvez trouve decouvre decouvrir termine terminer
montre tele telephone telephones bouton boutons appareil appareils sante
rapport pourquoi comment quel quelle quels quelles avec sans fort lampe
allume eteins mets ou aspirateur menage monte baisser baissez baisse monter
regle reglez verifie verfiez diagnostic diagnostics reseau session restaure
deconnexion deconnecte deconnectent disque porte entree redemarre redemarrer
ouvre ouvrir formatte formate enleve enlever retire retirer deplace deplacer
transfere bouge bouger arretez arrete arreter demarrez demarre demarrer
commence commencer annule annuler pause'''.split())

_EN = frozenset('''the and is are was were what why how which with my your his
her our their this that these those than then there here do does did done can
could will would please turn turns find finds run runs start starts stop stops
press put puts move moves remove removes migrate discover discovers finish
finished nearby through devices device vacuum'''.split())
# Deliberately excluded (loanwords or cross-language collisions, no signal):
# scan, bluetooth, ble, volume, tv, wifi, a, me, met, son, set, check.

_UNKNOWN = 'unknown'


def detect_lang(text):
    """'fr' | 'en' | 'unknown' by function-word majority (ties -> unknown)."""
    toks = tokens(fold(text))
    if not toks:
        return _UNKNOWN
    fr = sum(1 for w in toks if w in _FR)
    en = sum(1 for w in toks if w in _EN)
    if fr > en:
        return 'fr'
    if en > fr:
        return 'en'
    return _UNKNOWN


def lang_or_hint(text, hint=None):
    lang = detect_lang(text)
    if lang != _UNKNOWN:
        return lang
    return hint if hint in ('fr', 'en') else 'en'


# ---------------------------------------------------------------------------
# Single-reading STT repairs (matching only; never shown, never commanding)
# ---------------------------------------------------------------------------

# Observed on Watch7 audio (voice-watch-direct-01nov.md): 'tellée'.
# 'bluetouth/bloutouth/blutooth' and the splits below are synthetic but
# principled (STT word-segmentation errors); each maps to exactly one reading.
_TOKEN_REPAIRS = {
    'tellee': 'tele', 'telee': 'tele',
    'bluetouth': 'bluetooth', 'bloutouth': 'bluetooth', 'blutooth': 'bluetooth',
}
_COMPOUND_REPAIRS = (
    (re.compile(r'\bblue\s+tooth\b'), 'bluetooth', 'blue tooth->bluetooth'),
    (re.compile(r'\bfree\s+box\b'), 'freebox', 'free box->freebox'),
)
# 'telle' is also a French word ("une telle option"), so it is repaired only
# in device-indicating position (after la/ma/sur/...), never blindly.
_TELLE_RX = re.compile(
    r'\b(la|ma|ta|sa|sur|vers|de|du|le|mon|ton|son)\s+telle\b')


def repair(folded):
    """Return (fixed, repairs) with single-reading STT errors corrected."""
    fixed, repairs = folded, []
    for rx, to, label in _COMPOUND_REPAIRS:
        if rx.search(fixed):
            fixed = rx.sub(to, fixed)
            repairs.append(label)
    words = fixed.split()
    for i, w in enumerate(words):
        if w in _TOKEN_REPAIRS:
            words[i] = _TOKEN_REPAIRS[w]
            repairs.append('%s->%s' % (w, words[i]))
    fixed = ' '.join(words)
    if _TELLE_RX.search(fixed):
        fixed = _TELLE_RX.sub(lambda m: m.group(1) + ' tele', fixed)
        repairs.append('telle->tele')
    return fixed, repairs


# ---------------------------------------------------------------------------
# Ambiguous STT verbs: mets/mas/mais/mes collapse in watch-mic audio.
# ---------------------------------------------------------------------------

_UNCERTAIN_LEAD = frozenset({'mas', 'mais', 'mes', 'mai'})
_UNCERTAIN_NOUNS_RX = re.compile(
    r'\b(boutons?|volumes?|controls?|controles?|panels?)\b')


def uncertain_verb(fixed):
    """True when the utterance opens with an STT-ambiguous verb + control noun.

    'mais les boutons...' (row W7-03) is uncertain; 'mais fais un
    diagnostic' is an ordinary conjunction ('diagnostic' is not a control
    noun) and stays trusted.
    """
    toks = tokens(fixed)
    if not toks:
        return False
    if not (set(toks[:2]) & _UNCERTAIN_LEAD):
        return False
    return bool(_UNCERTAIN_NOUNS_RX.search(fixed))


def normalize(transcript, lang_hint=None):
    """Fold + repair + language for one transcript. Never raises on text."""
    folded = fold(transcript)
    fixed, repairs = repair(folded)
    lang = lang_or_hint(transcript, lang_hint)
    return {'folded': folded, 'fixed': fixed, 'lang': lang,
            'lang_raw': detect_lang(transcript), 'repairs': repairs,
            'uncertain_verb': uncertain_verb(fixed), 'tokens': tokens(folded)}


# ---------------------------------------------------------------------------
# Screens. Each takes folded-or-fixed text and returns None (no hit) or a hit
# dict. Hits always mean clarification/refusal, never a command.
# Run screens on `fixed`: repairs may only upgrade unsupported -> clarify.
# ---------------------------------------------------------------------------

# Irreversible / privileged actions beyond the legacy voice_intent REFUSE list.
# Deliberately narrow: 'flash' only counts with a firmware object or as the
# verb ('allume le flash' = flashlight stays untouched); 'paye*' excludes
# 'pays' (FR 'country'); 'call/appelle' excluded (reflexive 'je m'appelle'
# collides); catalog skills (vacuum.empty_dust) stay model-routed.
_REFUSAL_EXTRA_RX = re.compile(
    r'\b(reboot\w*|redemarr\w*|restart\w*|'
    r'wip\w*|effac\w*|eras\w*|format\w*|'
    r'brick\w*|unbrick\w*|unlock\w*|deverrouill\w*|'
    r'pay\b|paying|payments?|paye[esrz]?|paie\w*|paiement|'
    r'buy\w*|bought|purchas\w*|achet\w*)\b'
    r'|\b(?:ouvr\w*|opens?|opening)\s+(la\s+porte|the\s+(?:front\s+|back\s+|'
    r'garage\s+|main\s+|side\s+)?door|le\s+portail|the\s+gate)\b'
    r'|\bflash\w*\s+(le\s+firmware|du\s+firmware|the\s+firmware|firmware|'
    r'micrologiciel|rom\b|bios|radio|modem|recovery)\b')
_FLASH_VERB_RX = re.compile(r'^flash\w*\b')
_DEVICE_NOUNS_RX = re.compile(
    r'\b(tv|teles?|television|televiseur|phones?|telephones?|portables?|'
    r'mobiles?|watch|montre|tablets?|tablettes?|freebox|vacuum|aspirateur)\b')


def screen_refusal_extra(fixed):
    if _REFUSAL_EXTRA_RX.search(fixed):
        return {'kind': 'refusal_extra'}
    if _FLASH_VERB_RX.search(fixed) and _DEVICE_NOUNS_RX.search(fixed):
        return {'kind': 'refusal_extra'}
    return None


# -- conflicting intents --------------------------------------------------------

_FINISH_RX = re.compile(
    r'\b(finish|end|terminer|termine|fin)\b.*\bsession\b'
    r'|\brestore\b|\brestaure\w*\b')
_OTHER_ACTION_RX = (
    ('discover', re.compile(
        r'\b(discov\w*|find|scan|decouvr\w*|trouv\w*|cherch\w*|'
        r'devices?|appareils?)\b')),
    ('ble_scan', re.compile(r'\b(bluetooth|ble)\b')),
    ('diagnose', re.compile(
        r'\b(diagnos\w*|report|rapport|check|verifi\w*|verifie\w*|'
        r'health|sante)\b')),
    ('why_disconnect', re.compile(
        r'\b(why|pourquoi)\b.*\b(disconnect\w*|deconnect\w*|drop\w*|'
        r'coupe\w*|perd\w*|lost)\b')),
)
_TV_RX = re.compile(r'\b(tv|teles?|television|televiseur)\b')
_PHONE_RX = re.compile(r'\b(phones?|telephones?|portables?|mobiles?)\b')
_BT_RX = re.compile(r'\b(bluetooth|ble)\b')
_START_RX = re.compile(
    r'\b(starts?|starting|begin|begins|demarre\w*|commence\w*|'
    r'lance\w*)\b')
_STOP_RX = re.compile(
    r'\b(stops?|stopping|pauses?|pausing|cancels?|arrete\w*|'
    r'annule\w*)\b')


def screen_conflict(fixed):
    """One utterance, two actions: finish-vs-action, tv-vs-phone, go-vs-stop."""
    if _FINISH_RX.search(fixed):
        for name, rx in _OTHER_ACTION_RX:
            if rx.search(fixed):
                return {'kind': 'finish', 'other': name}
    if _TV_RX.search(fixed) and _PHONE_RX.search(fixed) and _BT_RX.search(fixed):
        return {'kind': 'targets'}
    if _START_RX.search(fixed) and _STOP_RX.search(fixed):
        return {'kind': 'startstop'}
    return None


# -- control presses and control references ---------------------------------

_PRESS_VERBS_RX = re.compile(
    r'\b(press\w*|push\w*|taps?|tapping|click\w*|clique\w*|'
    r'appuie\w*|appuyez|touches?|touchez|utilise\w*|use|uses|using)\b')
_BUTTON_NOUNS_RX = re.compile(
    r'\b(buttons?|boutons?|controls?|controles?|panels?|manettes?|'
    r'touches?|cles?|keys?)\b')
_VOLUME_UP_RX = re.compile(
    r'\bvolumes?\b.*\b(plus|up|more|haut|monte|louder)\b'
    r'|\b(plus|up|more|haut|monte|louder)\b.*\bvolumes?\b')
_CONTROL_ID_RX = re.compile(r'\bctl[ -]([0-9a-f]{4,64})[ -]g(\d+)\b')
_FILLER_LABEL = frozenset({'the', 'a', 'an', 'le', 'la', 'les', 'des', 'du',
                            'de', 'mon', 'ma', 'mes', 'my', 'button', 'bouton',
                            'boutons', 'buttons', 'control', 'controle'})


def screen_control_press(fixed):
    if _PRESS_VERBS_RX.search(fixed) and (
            _BUTTON_NOUNS_RX.search(fixed) or _VOLUME_UP_RX.search(fixed)):
        return {'kind': 'press'}
    return None


def _label_tokens(label):
    return [w for w in tokens(fold(label))
            if w not in _FILLER_LABEL and (len(w) >= 3 or w in ('tv', 'pc'))]


def check_control_reference(fixed, active_labels=(), revoked_labels=(),
                            active_ids=()):
    """Classify a transcript that may reference a generated control.

    verdict: 'revoked' (stale id or revoked label -> refuse), 'press_active'
    (press phrasing on a live label -> clarify: voice still cannot press),
    'press_unknown' (press phrasing, nothing matched -> clarify),
    'none' (no control reference at all).
    """
    words = set(tokens(fixed))
    found = _CONTROL_ID_RX.findall(fixed)
    if found:
        # Folded text carries spaces ('ctl a975 g1'); compare canonical ids.
        ids = ['ctl-%s-g%s' % (hexpart, gen) for hexpart, gen in found]
        if all(i in (active_ids or ()) for i in ids):
            return {'verdict': 'press_active', 'ids': ids}
        return {'verdict': 'revoked', 'ids': ids,
                'reason': 'stale or unknown control id'}
    for label in revoked_labels or ():
        toks = _label_tokens(label)
        if toks and all(t in words for t in toks):
            return {'verdict': 'revoked', 'label': label}
    if not screen_control_press(fixed):
        return {'verdict': 'none'}
    for label in active_labels or ():
        toks = _label_tokens(label)
        if toks and all(t in words for t in toks):
            return {'verdict': 'press_active', 'label': label}
    return {'verdict': 'press_unknown'}


# -- control-surface moves ----------------------------------------------------

_MOVE_VERBS_RX = re.compile(
    r'\b(moves?|moving|removes?|removing|migrates?|migrating|puts?|putting|'
    r'transfers?|deplaces?|deplacer|enleves?|enlever|retires?|retirer|'
    r'mets?|mettez|transferes?|transferer|bouges?|bouger)\b')
_MIGRATION_NOUNS_RX = re.compile(
    r'\b(buttons?|boutons?|controls?|controles?|panels?|manettes?)\b')
_INTERFACE_NOUNS_RX = re.compile(
    r'\b(watch|montre|tv|teles?|television|televiseur|phones?|telephones?|'
    r'portables?|mobiles?|tablets?|tablettes?|pcs?|computers?|'
    r'ordinateurs?|freebox)\b')


def screen_migration_shape(fixed):
    """Move/remove/put + control noun + interface noun (Watch7 rows land here)."""
    verb = bool(_MOVE_VERBS_RX.search(fixed))
    if not verb and uncertain_verb(fixed):
        verb = True  # 'mas/mais les boutons...' reads as a move verb
    return {'kind': 'migration'} if (
        verb and _MIGRATION_NOUNS_RX.search(fixed)
        and _INTERFACE_NOUNS_RX.search(fixed)) else None


# -- volume -------------------------------------------------------------------

_VOLUME_CORE_RX = re.compile(r'\bvolumes?\b')
_SOUND_RX = re.compile(r'\b(sons?|sounds?)\b')
_DIR_RX = re.compile(
    r'\b(ups?|downs?|plus|moins|monte\w*|baiss\w*|augmente\w*|'
    r'diminue\w*|louder|quieter|forts?|bas)\b')
_FORT_RX = re.compile(r'\b(plus|moins)\s+forts?\b')
# Strong direction words pair with a device noun ('louder on the TV').
# Bare up/down are excluded ('look up the TV manual' must not trip).
_DIR_STRONG_RX = re.compile(
    r'\b(louder|quieter|monte\w*|baiss\w*|augmente\w*|diminue\w*)\b')


def screen_volume_shape(fixed):
    if _VOLUME_CORE_RX.search(fixed):
        return {'kind': 'volume'}
    if _FORT_RX.search(fixed):
        return {'kind': 'volume'}
    if _SOUND_RX.search(fixed) and (
            _DIR_RX.search(fixed) or _DEVICE_NOUNS_RX.search(fixed)):
        return {'kind': 'volume'}
    if _DIR_STRONG_RX.search(fixed) and _DEVICE_NOUNS_RX.search(fixed):
        return {'kind': 'volume'}
    return None


# -- locate-my-device (no such skill exists: always clarify) -------------------

_LOCATE_VERBS_RX = re.compile(
    r'\b(finds?|finding|trouves?|trouver|retrouves?|retrouver|'
    r'cherches?|chercher|locates?|localises?|localiser|'
    r'ou\s+est|where\s+is)\b')
_LOCATE_DEVICES_RX = re.compile(
    r'\b(phones?|telephones?|portables?|montre|watch)\b')
_LOCATE_EXCLUDE_RX = re.compile(
    r'\b(bluetooth|ble|scans?|scanning|vacuum|aspirateur|tvs?|teles?|'
    r'television|televiseur|devices?|appareils?|discov\w*|decouvr\w*)\b')


def screen_locate_shape(fixed):
    if (_LOCATE_VERBS_RX.search(fixed)
            and _LOCATE_DEVICES_RX.search(fixed)
            and not _LOCATE_EXCLUDE_RX.search(fixed)):
        return {'kind': 'locate'}
    return None


# -- fragments ------------------------------------------------------------------

def is_fragment_match(intent, folded):
    """True when a matched intent rests on a bare, context-free trigger."""
    n = len(tokens(folded))
    if intent == 'discover':
        return n <= 2  # 'scan', 'find' alone: discovery-vs-BLE unclear
    if intent == 'diagnose':
        return n <= 2  # 'check', 'verifie' alone: report-vs-probe unclear
    return False


def is_short(folded):
    """1..3 surviving tokens with no match: guidance beats a dead end."""
    n = len(tokens(folded))
    return 1 <= n <= 3


# ---------------------------------------------------------------------------
# Localized clarification questions and refusal texts (input language wins)
# ---------------------------------------------------------------------------

QUESTIONS = {
    'press': {
        'en': "Voice can't press buttons. Press the button on the device "
              'screen instead.',
        'fr': 'La voix ne peut pas appuyer sur les boutons. Appuyez sur le '
              "bouton à l'écran de l'appareil."},
    'migration': {
        'en': 'To move controls between devices, use the migration screen on '
              "your PC: voice can't move controls. What did you want to move, "
              'and to which device?',
        'fr': "Pour déplacer des contrôles d'un appareil à un autre, utilisez "
              "l'écran de migration sur le PC : la voix ne déplace pas les "
              'contrôles. Que vouliez-vous déplacer, et vers quel appareil ?'},
    'volume': {
        'en': "Set an exact volume, or step up/down? Voice can't change "
              'volume by itself — use the on-screen TV controls.',
        'fr': "Régler un volume exact, ou monter/baisser d'un cran ? La voix "
              "ne règle pas le volume — utilisez les contrôles TV à l'écran."},
    'locate': {
        'en': "Locate your phone, or run a network discovery? Voice can't "
              "locate devices — say 'discover my devices' for discovery.",
        'fr': 'Localiser votre téléphone, ou découvrir le réseau ? La voix '
              'ne localise pas les appareils — dites '
              '« découvre mes appareils » pour la découverte.'},
    'fragment_discover': {
        'en': 'Scan what: nearby network devices, or Bluetooth via the TV '
              'or phone?',
        'fr': 'Scanner quoi : les appareils du réseau, ou le Bluetooth via '
              'la télé ou le téléphone ?'},
    'fragment_diagnose': {
        'en': 'Check what: a full diagnostic report, or a disconnect probe?',
        'fr': 'Vérifier quoi : un rapport de diagnostic complet, ou une '
              'sonde de déconnexion ?'},
    'guidance': {
        'en': "I didn't catch that. Try e.g. 'discover my devices', "
              "'bluetooth scan via the TV', 'run a diagnostic'.",
        'fr': "Je n'ai pas compris. Essayez par exemple : "
              '« découvre mes appareils », « scan bluetooth via la télé », '
              '« fais un diagnostic ».'},
    'uncertain': {
        'en': 'I may have misheard the action — could you rephrase? '
              'Nothing was run.',
        'fr': "J'ai peut-être mal entendu l'action — pouvez-vous reformuler ? "
              "Rien n'a été exécuté."},
    'repaired': {
        'en': 'I may have misheard — did you mean "{guess}"? Rephrase or '
              'pick on screen.',
        'fr': 'J\u2019ai peut-être mal entendu — vouliez-vous dire '
              '« {guess} » ? Reformulez ou choisissez à l\u2019écran.'},
    'refusal_extra': {
        'en': 'This request needs a manual, explicitly confirmed action; '
              'voice cannot start it.',
        'fr': 'Cette demande exige une action manuelle explicitement '
              'confirmée ; la voix ne peut pas la lancer.'},
    'conflict_targets': {
        'en': 'Bluetooth via the TV or via the phone? Say one device.',
        'fr': 'Bluetooth via la télé ou via le téléphone ? Dites un seul '
              'appareil.'},
    'conflict_startstop': {
        'en': 'Start or stop? Say one action.',
        'fr': 'Démarrer ou arrêter ? Dites une seule action.'},
}

_CONFLICT_OTHER = {
    'discover': ('discovering devices', 'découvrir les appareils'),
    'ble_scan': ('a Bluetooth scan', 'un scan Bluetooth'),
    'diagnose': ('a diagnostic', 'un diagnostic'),
    'why_disconnect': ('a disconnect probe', 'une sonde de déconnexion'),
}

_REPAIRED_GUESS = {
    'discover': ('discover my devices', 'découvre mes appareils'),
    'ble_scan_via_tv': ('a Bluetooth scan via the TV',
                        'un scan Bluetooth via la télé'),
    'ble_scan_via_phone': ('a Bluetooth scan via the phone',
                           'un scan Bluetooth via le téléphone'),
    'diagnose': ('a diagnostic', 'un diagnostic'),
    'why_disconnect': ('why it disconnects', 'pourquoi ça se déconnecte'),
    'finish_session': ('finish the session', 'termine la session'),
}


def question(kind, lang):
    lang = 'fr' if lang == 'fr' else 'en'
    return QUESTIONS[kind][lang]


def conflict_finish_question(other, lang):
    name = _CONFLICT_OTHER.get(other, _CONFLICT_OTHER['discover'])
    if lang == 'fr':
        return ('Votre demande mélange deux actions : « %s » et '
                '« terminer la session ». Laquelle voulez-vous ?') % name[1]
    return ('Your request mixes two actions: "%s" and "finish the session". '
            'Which one do you want?') % name[0]


def repaired_question(intent, lang):
    guess = _REPAIRED_GUESS.get(intent, _REPAIRED_GUESS['discover'])
    text = question('repaired', lang)
    return text.format(guess=guess[1] if lang == 'fr' else guess[0])


# ---------------------------------------------------------------------------
# Drain entry point: deterministic fail-closed screens for STT transcripts.
# Volume is deliberately NOT screened here: the model tier may legitimately
# resolve 'monte le son' to tv_volume_step, and pre-empting it would be a
# regression. Everything screened here has no legitimate model resolution
# (refusals, conflicts, presses, moves, locate-my-device).
# ---------------------------------------------------------------------------

def screen_voice_transcript(transcript, lang_hint=None):
    """None (no screen: route to the model tier) or {'status', 'text'}."""
    norm = normalize(transcript, lang_hint)
    fixed, lang = norm['fixed'], norm['lang']
    if not fixed:
        return None
    if screen_refusal_extra(fixed):
        return {'status': 'unsupported', 'text': question('refusal_extra', lang)}
    if screen_control_press(fixed):
        return {'status': 'needs_clarification',
                'text': question('press', lang)}
    if screen_migration_shape(fixed):
        return {'status': 'needs_clarification',
                'text': question('migration', lang)}
    if screen_locate_shape(fixed):
        return {'status': 'needs_clarification',
                'text': question('locate', lang)}
    conflict = screen_conflict(fixed)
    if conflict:
        if conflict['kind'] == 'finish':
            text = conflict_finish_question(conflict['other'], lang)
        elif conflict['kind'] == 'targets':
            text = question('conflict_targets', lang)
        else:
            text = question('conflict_startstop', lang)
        return {'status': 'needs_clarification', 'text': text}
    return None
