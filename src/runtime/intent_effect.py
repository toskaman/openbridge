"""FINAL FRONTIER S8: intent/effect agreement gate for NL plans.

A proposal can pass every shape/skill/target/param check and still be the
WRONG action: ModelStudy48 caught Llama 3B turning a factory-reset demand
into a settings-app launch, a root-panel demand into a YouTube launch, and
a stranger's phone into the owner's phone (H-R07/R08/R09, unsafe_exec=6).
Shape validation cannot see that; this gate compares the REQUEST against
the PROPOSED EFFECT and blocks the mismatch before execution approval.

Rules (deterministic, EN/FR, no model calls). The gate is a pre-approval
filter, never the sole authorization: skill/target/param validators and
owner consent still decide downstream.
1. Must-refuse markers (approval evasion, destructive/privileged effects,
   physical access) anywhere in the request -> the whole proposal refuses.
2. Other-owner markers (stranger's, neighbor's, next door, ...) -> refuse:
   the named device cannot be any live device, so any live target is a
   substitution.
3. Per step, the skill's effect vocabulary must overlap the request, else
   the step clarifies (unrelated substitution, off-manifest effect).
4. Per targeted step, the target must correspond to a device reference in
   the request (canonical synonyms: tv/television/tele, tablet/slate, ...),
   unless the request names no device at all (scenes like "quiet mode").
   A room/label word naming a DIFFERENT live device than the step target
   (and targeted by no step) clarifies instead of silently mistargeting.

Detected boundaries (documented, not hidden):
- Same-class instance ambiguity ("set the volume on the tv" with two TVs)
  passes when the effect matches: the consent preview shows the target and
  the owner decides. The gate catches unrelated substitution, not ambiguity.
- "Show me the garage door camera" clarifies (no effect overlap) rather
  than refusing with UNKNOWN_DEVICE: execution is still blocked.
- "Clean up" + a vacuum proposal passes the effect check (clean/vacuum are
  related); WHAT to clean stays the model's clarification job.
- FR pc_run ("lance chkdsk") is uncovered: "lance" belongs to app_launch.
  EN "run/execute" and FR "execute une commande" are covered.
"""
import re

from src.ai.voice_normalize import fold, tokens

REFUSAL = 'refusal'
CLARIFICATION = 'clarification'


class IntentEffectError(ValueError):
    def __init__(self, kind, code, detail):
        super().__init__('%s %s: %s' % (kind, code, detail))
        self.kind = kind
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Must-refuse markers (regexes over folded text). Order is reporting order.
# ---------------------------------------------------------------------------
_REFUSAL_RES = (
    # Approval evasion: the request waives the consent the gate exists for.
    (re.compile(r'\bwithout asking\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bno questions\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bdont ask\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bdo not ask\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bskip( the)? approval\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bwithout approval\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\balready said yes\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bsilently\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bsans demander\b'), 'APPROVAL_EVASION'),
    (re.compile(r'\bsans autorisation\b'), 'APPROVAL_EVASION'),
    # Destructive / privileged effects no skill may ever satisfy.
    (re.compile(r'\bfactory\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bdelet\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\beras\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\beffac\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bformat\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bsupprim\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\broot\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bbootloader\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bjailbreak\w*\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bshell\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\brm\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bwipe\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bbrick\w*\b'), 'DESTRUCTIVE_EFFECT'),
    (re.compile(r'\bunlock\w*\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bdeverrouill\w*\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\badmin\w*\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bpassword\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bpasswd\b'), 'PRIVILEGED_EFFECT'),
    (re.compile(r'\bcredential\w*\b'), 'PRIVILEGED_EFFECT'),
    # Physical access: opening a door/gate is never an app launch.
    (re.compile(r'\b(?:ouvr\w*|opens?|opening)\s+(la\s+porte|the\s+(?:front\s+|'
                r'back\s+|garage\s+|main\s+|side\s+)?door|le\s+portail|'
                r'the\s+gate)\b'), 'PHYSICAL_ACCESS'),
)

# The request names a device that cannot be in this fabric: somebody else's.
_OTHER_OWNER_RES = (
    (re.compile(r'\bstrangers?\b'), 'OTHER_OWNER_DEVICE'),
    (re.compile(r'\bneighbours?\b'), 'OTHER_OWNER_DEVICE'),
    (re.compile(r'\bvoisins?\b'), 'OTHER_OWNER_DEVICE'),
    (re.compile(r'\bnext door\b'), 'OTHER_OWNER_DEVICE'),
    (re.compile(r'\bsomeone else\b'), 'OTHER_OWNER_DEVICE'),
)

# Host self-references in destination position ("onto this computer") name no
# step target; strip them before device-reference extraction.
_HOST_DEST_RX = re.compile(r'\b(onto|into|vers)\s+this\s+\w+')

# ---------------------------------------------------------------------------
# Canonical device classes (folded synonyms). Single letters never match.
# ---------------------------------------------------------------------------
_CANON = {}
for _cls, _words in {
        'tv': {'tv', 'tvs', 'television', 'televisions', 'tele', 'teles',
               'televiseur', 'televiseurs'},
        'phone': {'phone', 'phones', 'telephone', 'telephones', 'portable',
                  'portables', 'mobile', 'mobiles'},
        'tablet': {'tablet', 'tablets', 'tablette', 'tablettes', 'slate',
                   'slates'},
        'vacuum': {'vacuum', 'vacuums', 'robot', 'robots', 'aspirateur',
                   'aspirateurs'},
        'pc': {'pc', 'pcs', 'computer', 'computers', 'ordinateur',
               'ordinateurs'},
        'watch': {'watch', 'watches', 'montre', 'montres'},
        'freebox': {'freebox'},
        'router': {'router', 'routers', 'routeur', 'routeurs'},
}.items():
    for _w in _words:
        _CANON[_w] = _cls

# ---------------------------------------------------------------------------
# Effect vocabulary per skill (folded tokens). Deliberately small: generic
# verbs (set, make, do, put, get, use, play, show) match nothing on purpose --
# an effect the request never names is exactly what the gate must catch.
# ---------------------------------------------------------------------------
_VOLUME = frozenset({'volume', 'volumes', 'up', 'down', 'lower', 'lowered',
                     'higher', 'raise', 'raised', 'quieter', 'louder', 'hush',
                     'hushed', 'quiet', 'quieter', 'mute', 'muted', 'unmute',
                     'tick', 'ticks', 'level', 'levels', 'son', 'baisser',
                     'baisse', 'baissez', 'monter', 'monte', 'montez', 'fort',
                     'muet', 'muette', 'sourdine', 'silence', 'silenced'})

EFFECT_VOCAB = {
    'app_launch': frozenset({'launch', 'launches', 'launched', 'open', 'opens',
                             'opened', 'opening', 'start', 'starts', 'started',
                             'starting', 'app', 'apps', 'application',
                             'applications', 'lance', 'lancer', 'ouvre',
                             'ouvrir', 'demarre', 'demarrer'}),
    'ble_scan_room': frozenset({'listen', 'listens', 'listening', 'scan',
                                'scans', 'scanning', 'scanned', 'bluetooth',
                                'ble', 'wireless', 'peripherals', 'peripheral',
                                'nearby', 'discover', 'discovers', 'discovery',
                                'detect', 'detects', 'detection', 'detecte',
                                'scanner', 'recherche'}),
    'capability_probe': frozenset({'what', 'capabilities', 'capability',
                                   'capable', 'skills', 'features', 'peut',
                                   'peuvent', 'fonctions', 'possibilites'}),
    'capture_montage': frozenset({'stitch', 'stitched', 'stitches',
                                  'stitching', 'combine', 'combines',
                                  'combined', 'merge', 'merges', 'merged',
                                  'montage', 'assembler', 'assemble',
                                  'fusionner', 'fusionne'}),
    'capture_send': frozenset({'beam', 'beams', 'beamed', 'send', 'sends',
                               'sending', 'sent', 'grab', 'grabs', 'grabbed',
                               'cap', 'caps', 'envoie', 'envoyer'}),
    'device_facts': frozenset({'report', 'reports', 'reported', 'file',
                               'files', 'facts', 'fact', 'particulars',
                               'details', 'detail', 'info', 'information',
                               'stored', 'dossier', 'fiche', 'rapport',
                               'infos', 'renseignements'}),
    'file_pull': frozenset({'fetch', 'fetches', 'fetched', 'pull', 'pulls',
                            'pulled', 'download', 'downloads', 'downloaded',
                            'retrieve', 'retrieves', 'retrieved', 'copy',
                            'copies', 'telecharge', 'telecharger',
                            'recupere', 'recuperer'}),
    'file_push': frozenset({'store', 'stores', 'stored', 'push', 'pushes',
                            'pushed', 'upload', 'uploads', 'uploaded', 'save',
                            'saves', 'saved', 'transfer', 'transfers',
                            'transferred', 'copy', 'copies', 'stocke',
                            'stocker', 'transfere', 'transferer',
                            'enregistre', 'enregistrer'}),
    'pc_run': frozenset({'run', 'runs', 'running', 'execute', 'executes',
                         'executed', 'command', 'commands', 'executer',
                         'commande', 'commandes'}),
    'retro_command': frozenset({'retro', 'emulator', 'emulators', 'emulate',
                                'freeze', 'freezes', 'frozen', 'console',
                                'consoles', 'emulateur', 'emulateurs',
                                'geler', 'figer'}),
    'screen_capture': frozenset({'snap', 'snaps', 'snapped', 'snapshot',
                                 'snapshots', 'capture', 'captures',
                                 'captured', 'capturing', 'screenshot',
                                 'screenshots', 'photo', 'photos', 'picture',
                                 'pictures', 'display', 'displays', 'screen',
                                 'screens', 'ecran', 'ecrans',
                                 'photographie'}),
    'tv_volume_set': _VOLUME,
    'tv_volume_step': _VOLUME,
    'vacuum_command': frozenset({'vacuum', 'vacuums', 'robot', 'robots',
                                 'cleaning', 'cleaner', 'cleaners', 'clean',
                                 'cleans', 'cleaned', 'aspirateur',
                                 'aspirateurs', 'dock', 'docks', 'docked',
                                 'docking', 'park', 'parks', 'parked',
                                 'parking', 'dust', 'empty', 'emptied', 'bin',
                                 'charge', 'charging', 'start', 'starts',
                                 'stop', 'stops', 'pause', 'paused', 'resume',
                                 'resumed', 'quiet', 'quietly', 'silence',
                                 'silenced', 'demarre', 'demarrer', 'arrete',
                                 'arreter', 'arret', 'nettoie', 'nettoyer',
                                 'menage', 'aspire', 'aspirer', 'station',
                                 'recharge'}),
}


def _canon(token):
    return _CANON.get(token, token)


def _words(text):
    return [t for t in tokens(fold(text)) if len(t) > 1]


def _request_sets(text):
    """(word set, canonical set) with host-destination phrases stripped."""
    stripped = _HOST_DEST_RX.sub(' ', fold(text))
    words = [t for t in tokens(stripped) if len(t) > 1]
    return set(words), {_canon(t) for t in words}


def _label_words(label):
    return {_canon(t) for t in _words(label or '')}


def check(text, spec, devices):
    """Raise IntentEffectError when the validated spec mismatches the request.

    spec is the output of nl_plan._spec_from_steps (validated steps); devices
    is the live snapshot device list. Returns None when every step
    corresponds to the request in both effect and target.
    """
    folded = fold(text)
    for rx, code in _REFUSAL_RES:
        if rx.search(folded):
            raise IntentEffectError(
                REFUSAL, code,
                'request calls for %s; no proposal may satisfy it' % code.lower())
    for rx, code in _OTHER_OWNER_RES:
        if rx.search(folded):
            raise IntentEffectError(
                REFUSAL, code,
                'request names a device outside this fabric; any live target '
                'would be a substitution')
    _, req = _request_sets(text)
    steps = (spec or {}).get('steps') or []
    live_labels = [d.get('label') for d in devices or [] if d.get('label')]
    label_vocab = set()
    for label in live_labels:
        label_vocab |= _label_words(label)
    # A request names a device when it carries a canonical device token or
    # a live label word; anything else (scenes, probes) skips target checks.
    names_device = bool(req & (set(_CANON.values()) | label_vocab))
    targeted = {label for label in live_labels
                for s in steps if s.get('target') == label}
    for i, step in enumerate(steps, 1):
        skill = step.get('skill_id')
        vocab = EFFECT_VOCAB.get(skill)
        if vocab is None or not (req & vocab):
            raise IntentEffectError(
                CLARIFICATION, 'EFFECT_UNRELATED',
                'step %d (%s) matches no effect named in the request' % (i, skill))
        target = step.get('target')
        if not target or target == 'fabric' or not names_device:
            continue
        words = _label_words(target)
        if words & req:
            pass
        else:
            raise IntentEffectError(
                CLARIFICATION, 'TARGET_UNRELATED',
                'step %d targets %r, named nowhere in the request' % (i, target))
        for word in sorted(req & label_vocab):
            owners = [label for label in live_labels if word in _label_words(label)]
            if target not in owners and not (set(owners) & targeted):
                raise IntentEffectError(
                    CLARIFICATION, 'TARGET_ROOM_MISMATCH',
                    'step %d targets %r but the request names %r' % (i, target, word))
    return None
