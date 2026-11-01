"""Campaign Two D2: deterministic context-aware NL follow-up resolution.

Sits ON TOP of the existing router (src/runtime/nl_router.py, untouched):
pronoun/ellipsis follow-ups ("pause it", "that one", "monte-le", "plus fort")
are resolved against the prior turn's intent, and keyword candidates are
re-ranked against the live capability graph (skills with no live target
device are demoted, never guessed).

Deterministic only: no model calls, no network, no randomness. Every
function is pure except parse_with_context's delegated N.parse call.
Refusals stay refusals: incompatible families, ties and missing priors
return None so the caller falls through to the normal router path.
"""
import re
import unicodedata

from src.runtime import intent as I
from src.runtime import skills as S

# Standalone reference tokens (lowercased, word-boundary matched).
_EN_PRONOUNS = ('it', 'its', 'that', 'this', 'them', 'that one', 'this one')
_FR_PRONOUNS = ('le', 'la', 'les', 'lui', 'elle', 'eux', 'ça', 'ca',
                'celui-ci', 'celui-la', 'celle-ci', 'celle-la', 'celui-là',
                'celle-là', 'cet appareil', 'cette appareil')
# Hyphenated/contracted FR clitics: "mets-le", "monte-le", "baisse-la".
_FR_CLITIC_RE = re.compile(r"-(le|la|les|lui|leur)\b", re.IGNORECASE)
# Bare-ellipsis follow-ups: no noun at all ("louder", "plus fort", "pause").
_EN_ELLIPSIS = (('louder',), ('quieter',), ('pause',), ('louder', 'please'))
_FR_ELLIPSIS = ((('plus', 'fort'), ('moins', 'fort'), ('en', 'pause')))

# Nouns that name an explicit target: their presence means NOT a follow-up.
# Capability words (volume/son) are deliberately absent: naming WHAT without
# WHICH device is still a follow-up ("monte le son" needs the prior target).
_EXPLICIT_NOUNS = ('tv', 'télé', 'tele', 'television', 'vacuum', 'aspirateur',
                   'robot', 'relay', 'relais', 'phone', 'téléphone', 'telephone',
                   'fabric', 'bluetooth', 'ble', 'device', 'appareil', 'devices')

# Follow-up synonym expansion (local to this module; the shared skill catalog
# is untouched). Maps colloquial follow-up words onto catalog keywords.
SYNONYMS = {'louder': 'up', 'quieter': 'down', 'lower': 'down', 'raise': 'up',
            'plus fort': 'up', 'moins fort': 'down', 'monte': 'up', 'monter': 'up',
            'baisse': 'down', 'baisser': 'down', 'home': 'dock', 'rentrer': 'dock',
            'menage': 'clean', 'nettoyage': 'clean', 'demarre': 'start',
            'lance': 'start', 'commence': 'start', 'vide': 'empty',
            'trouve': 'find', 'cherche': 'find', 'recharge': 'charge'}

_FAMILY_OF_TARGET = {'tv': 'tv', 'vacuum': 'vacuum', 'relay': 'relay',
                     'any': 'any', 'fabric': 'fabric'}

STATUS_OK = ('resolved', 'approved', 'executed')


def _norm(text):
    return (text or '').strip().lower()


def _fold(text):
    """Lowercased, accent-stripped text for keyword matching (démarre->demarre)."""
    nfkd = unicodedata.normalize('NFKD', _norm(text))
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def scoring_text(text):
    """Follow-up words minus the reference itself: candidates must match what
    the user SAID, never the injected prior noun (which would tie a family)."""
    t = _FR_CLITIC_RE.sub(' ', _norm(text))
    for p in sorted(set(_EN_PRONOUNS) | set(_FR_PRONOUNS), key=len, reverse=True):
        t = re.sub(r'\b%s\b' % re.escape(p), ' ', t)
    return ' '.join(t.split())


def has_explicit_target(text):
    """True when the text names a device/capability noun itself."""
    hay = ' %s ' % re.sub(r'[^\wàâäéèêëîïôöùûüç\- ]', ' ', _norm(text))
    hay = hay.replace('-', ' ')
    for noun in _EXPLICIT_NOUNS:
        if ' %s ' % noun in hay:
            return True
    return False


def detect_reference(text, lang='en'):
    """True when the text refers to a prior turn (pronoun or bare ellipsis)."""
    t = _norm(text)
    if not t or has_explicit_target(text):
        return False
    words = re.findall(r"[\wàâäéèêëîïôöùûüç]+", t)
    bag = set(words)
    joined = ' '.join(words)
    if lang == 'fr':
        if _FR_CLITIC_RE.search(t):
            return True
        if any(p in bag or p in joined for p in _FR_PRONOUNS):
            return True
        return any(set(e) <= bag for e in _FR_ELLIPSIS)
    if any(p == joined or ' %s ' % p in ' %s ' % joined for p in _EN_PRONOUNS):
        return True
    if any(p in bag for p in ('it', 'that', 'this', 'them')):
        return True
    return any(set(e) <= bag and len(bag - set(e)) <= 1 for e in _EN_ELLIPSIS)


def prior_family(prior_doc):
    """Target family of a prior intent (tv/vacuum/relay/any/fabric/None)."""
    if not isinstance(prior_doc, dict):
        return None
    if prior_doc.get('status') not in STATUS_OK:
        return None
    c = S.get(prior_doc.get('skill_id'))
    if c is None or not prior_doc.get('targets'):
        return None
    fams = [_FAMILY_OF_TARGET.get(t) for t in c['targets']]
    fams = [f for f in fams if f]
    if not fams:
        return None
    return fams[0]


def compatible(skill_id, family):
    """A candidate skill may inherit prior targets only within its family."""
    if family is None:
        return False
    c = S.get(skill_id)
    if c is None:
        return False
    fams = {_FAMILY_OF_TARGET.get(t) for t in c['targets']}
    if 'fabric' in fams:
        return False  # fabric reads never inherit device targets
    return family in fams or 'any' in fams or family == 'any'


def rewrite(text, prior_doc):
    """Substitute the prior target noun into a follow-up; '' when unusable."""
    if not isinstance(prior_doc, dict) or not prior_doc.get('targets'):
        return ''
    ref = (prior_doc['targets'][0].get('ref') or '').strip().lower()
    if not ref:
        return ''
    noun = 'tv' if 'tv' in ref or 'télé' in ref else (
        'vacuum' if 'vac' in ref else ('relay' if 'relay' in ref else ref.split('-')[0]))
    t = (text or '').strip()
    # FR clitic first ("mets-le en pause" -> "mets vacuum en pause").
    t = _FR_CLITIC_RE.sub(' %s' % noun, t)
    # Then standalone pronouns, longest first.
    for p in sorted(set(_EN_PRONOUNS) | set(_FR_PRONOUNS), key=len, reverse=True):
        t = re.sub(r'\b%s\b' % re.escape(p), noun, t, flags=re.IGNORECASE)
    if t.strip().lower() == (text or '').strip().lower():
        t = '%s %s' % (t, noun)  # bare ellipsis: append the noun
    return ' '.join(t.split())


def rank_candidates(scored, devices=None):
    """Re-rank (base_score, skill_id) pairs against the live device graph.

    +1 when the skill's family has a live device (or is untargeted/fabric,
    and only when the base score is already positive -- the graph re-ranks
    keyword matches, it never invents a candidate from zero);
    -1 when targeted but no live device matches. Pure, deterministic;
    ties keep catalog order (sorted() is stable on the input order).
    devices=None means "no graph info" and leaves scores untouched; an
    explicit (possibly empty) graph applies boosts and demotions.
    """
    if devices is None:
        return sorted(scored, reverse=True)
    live = set()
    for d in (devices or {}).values():
        cat = (d.get('category') or '').strip().lower()
        if cat:
            live.add(cat)
    live.add('fabric')
    out = []
    for base, sid in scored:
        c = S.get(sid)
        if c is None:
            out.append((base - 1, sid))
            continue
        fams = {_FAMILY_OF_TARGET.get(t, t) for t in c['targets']}
        if 'any' in fams or 'fabric' in fams:
            out.append((base + 1 if base > 0 else base, sid))
        elif fams & live or 'relay' in fams:
            out.append((base + 1 if base > 0 else base, sid))
        else:
            out.append((base - 1, sid))
    return sorted(out, reverse=True)


def top_candidate(text, outcome='', devices=None, eligible=None):
    """Unique-best skill for a follow-up, capability-aware; None on tie/zero.

    Scores the follow-up's own words (reference stripped, accents folded,
    synonyms expanded) so the injected prior noun can never force a tie.
    `eligible`, when given, gates the candidate set BEFORE election (skills
    that cannot take the prior targets are not candidates at all).
    """
    hay = '%s %s' % (_fold(scoring_text(text)), _fold(outcome))
    for word, token in SYNONYMS.items():
        if word in hay:
            hay += ' ' + token
    if re.search(r'\d', hay):
        hay += ' set'  # an exact value selects set-over-step deterministically
    scored = [ (sum(1 for k in c['keywords'] if _fold(k) in hay), c['skill_id'])
               for c in S.all_skills()
               if eligible is None or eligible(c['skill_id']) ]
    if len(scored) < 2 or max(s for s, _ in scored) <= 0:
        return None  # graph boosts alone must never elect a keywordless candidate
    ranked = rank_candidates(sorted(scored, reverse=True), devices)
    if ranked[0][0] > ranked[1][0] and ranked[0][0] > 0:
        return ranked[0][1]
    return None


def resolve_followup(text, lang, prior_doc, devices=None):
    """Resolve a follow-up against the prior turn; None to fall through.

    Returns a validated resolved intent (provenance parser 'rules') or None
    when: no usable prior, no reference detected, no unique candidate, or
    the candidate is outside the prior target family.
    """
    if lang not in I.LANGS:
        return None
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        return None
    fam = prior_family(prior_doc)
    if fam is None or not detect_reference(text, lang):
        return None
    rewritten = rewrite(text, prior_doc)
    if not rewritten:
        return None
    # Score the user's own words (top_candidate strips the reference);
    # `rewritten` is only the human-readable outcome.
    sid = top_candidate(text, '', devices,
                         eligible=lambda c: compatible(c, fam))
    if sid is None:
        return None
    try:
        S.resolve(sid, {})
    except S.SkillError:
        return None
    doc = I.new_intent(text.strip(), lang)
    doc = dict(doc, status='resolved', skill_id=sid,
               outcome=rewritten[:300],
               targets=[dict(t) for t in prior_doc['targets']],
               params={}, confidence=0.6,
               ambiguities=['context-resolved follow-up of %s' % prior_doc.get('skill_id')])
    if I.validate_intent(doc):
        return None
    return doc


def parse_with_context(text, lang, quality, local_transport, prior_doc,
                       cloud_transport=None, medium_transport=None,
                       cloud_allowed=False, before_cloud=None, devices=None):
    """Router extension: context first, existing router untouched on miss."""
    hit = resolve_followup(text, lang, prior_doc, devices)
    if hit is not None:
        return hit
    from src.runtime import nl_router as N
    return N.parse(text, lang, quality, local_transport, cloud_transport,
                   medium_transport, cloud_allowed, before_cloud)
