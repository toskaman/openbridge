"""Dataset for the phone's own command model (Companion 0.15, AI on the phone).

The phone understands, without the PC or the internet, the orders it can carry out itself, and sends everything
else to the general model (or to the PC when it is there):

    {"a": "nav", "v": "next|ok|back|home"}              glasses navigation
    {"a": "module", "m": "<module>", "on": true|false}   oracle, messages, sport, tv, vacuum, sensors
    {"a": "profile", "p": "home|bike|work"}
    {"a": "sport", "v": "start|stop"}                    standalone sport session
    {"a": "luma", "v": "up|down|0-15"}                   glasses brightness
    {"a": "standalone", "on": true|false}
    {"a": "ask"}                                         anything else: a question for the general model, or an
                                                         order for another device (the PC's job)

French and English, spoken style (no accents, no punctuation, filler words). Templates are split between train and
test BEFORE expansion, so no test sentence shares a template with training.

    python dev/ai_training/make_phone_dataset.py --out D:/OpenBridgeAI/data_phone
"""
import argparse
import json
import random
import unicodedata
from pathlib import Path

SYSTEM = 'Tu es le routeur de commandes du telephone OpenBridge. Reponds uniquement en JSON compact.'

NAV = {
    'next': ['suivant', 'passe au suivant', 'ecran suivant', 'va au suivant', 'le suivant', 'd apres', 'continue',
             'next', 'next one', 'go next', 'next screen', 'move on', 'skip'],
    'ok': ['ouvre', 'ouvrir', 'valide', 'ouvre ca', 'selectionne', 'entre', 'choisis ca', 'lance ca',
           'open', 'open it', 'select', 'select this', 'enter', 'choose this'],
    'back': ['retour', 'reviens', 'precedent', 'en arriere', 'reviens en arriere', 'ecran precedent', 'annule',
             'back', 'go back', 'previous', 'previous screen', 'return'],
    'home': ['accueil', 'menu principal', 'retourne a l accueil', 'ecran d accueil', 'va au menu', 'retour au debut',
             'home', 'go home', 'main menu', 'home screen', 'back to the start'],
}
MODULE_WORDS = {
    # The glasses menus are named with "module" / "menu": "eteins la tele" means the TV itself (the PC's job).
    'oracle': {'fr': ['l oracle', 'oracle', 'le module oracle'], 'en': ['the oracle', 'oracle', 'the oracle module']},
    'messages': {'fr': ['le module messages', 'le menu messages', 'les messages sur les lunettes'],
                 'en': ['the messages module', 'the messages menu', 'messages on the glasses']},
    'sport': {'fr': ['le module sport', 'le menu sport', 'les ecrans sport'], 'en': ['the sport module', 'the sport menu', 'the sport screens']},
    'tv': {'fr': ['le module tele', 'le menu tele', 'le menu tv'], 'en': ['the tv module', 'the tv menu', 'the tv screen on the glasses']},
    'vacuum': {'fr': ['le module aspirateur', 'le menu aspirateur', 'le menu robot'], 'en': ['the vacuum module', 'the vacuum menu', 'the robot menu']},
    'sensors': {'fr': ['les capteurs', 'les capteurs du telephone', 'le module capteurs'], 'en': ['the sensors', 'the phone sensors', 'the sensors module']},
}
ON = {'fr': ['active {m}', 'allume {m}', 'mets {m}', 'remets {m}', 'je veux {m}', 'affiche {m}', 'ajoute {m}',
             'tu peux activer {m}', 'branche {m}'],
      'en': ['turn on {m}', 'enable {m}', 'switch on {m}', 'show {m}', 'add {m}', 'i want {m}', 'can you enable {m}',
             'bring back {m}']}
OFF = {'fr': ['desactive {m}', 'coupe {m}', 'eteins {m}', 'enleve {m}', 'retire {m}', 'cache {m}', 'je veux plus {m}',
              'tu peux couper {m}', 'masque {m}'],
       'en': ['turn off {m}', 'disable {m}', 'switch off {m}', 'hide {m}', 'remove {m}', 'no more {m}',
              'can you disable {m}', 'get rid of {m}']}
PROFILE = {
    'home': {'fr': ['passe en mode maison', 'profil maison', 'je suis a la maison', 'je rentre chez moi', 'mode maison'],
             'en': ['home profile', 'switch to home mode', 'i am home', 'i am back home', 'home mode']},
    'bike': {'fr': ['passe en mode velo', 'profil velo', 'je pars a velo', 'je vais rouler', 'mode velo', 'je monte sur le velo'],
             'en': ['bike profile', 'switch to bike mode', 'i am going cycling', 'going for a ride', 'bike mode']},
    'work': {'fr': ['passe en mode bureau', 'profil bureau', 'je suis au travail', 'j arrive au bureau', 'mode boulot'],
             'en': ['work profile', 'switch to work mode', 'i am at work', 'office mode', 'work mode']},
}
SPORT = {
    'start': {'fr': ['lance une seance', 'demarre le chrono', 'commence l entrainement', 'c est parti pour la sortie',
                     'demarre une sortie', 'top depart', 'lance le chrono'],
              'en': ['start a session', 'start the timer', 'start my workout', 'begin the ride', 'start a run', 'go go go']},
    'stop': {'fr': ['arrete la seance', 'stop le chrono', 'fin de l entrainement', 'j ai fini ma sortie', 'termine la seance'],
             'en': ['stop the session', 'stop the timer', 'end my workout', 'i am done', 'finish the run']},
}
LUMA = {
    'up': {'fr': ['plus lumineux', 'monte la luminosite', 'augmente la luminosite', 'j y vois rien c est trop sombre'],
           'en': ['brighter', 'turn up the brightness', 'increase the brightness', 'too dark']},
    'down': {'fr': ['moins lumineux', 'baisse la luminosite', 'diminue la luminosite', 'c est trop lumineux'],
             'en': ['dimmer', 'turn down the brightness', 'lower the brightness', 'too bright']},
}
LUMA_SET = {'fr': ['luminosite a {n}', 'mets la luminosite a {n}', 'regle la luminosite sur {n}'],
            'en': ['brightness {n}', 'set the brightness to {n}', 'brightness at {n}']}
STANDALONE = {True: {'fr': ['active le mode autonome', 'passe en mode autonome', 'mode sans pc', 'pilote les lunettes toi meme'],
                     'en': ['turn on standalone mode', 'standalone mode on', 'no pc mode', 'drive the glasses yourself']},
              False: {'fr': ['desactive le mode autonome', 'coupe le mode autonome', 'rends la main au pc'],
                      'en': ['turn off standalone mode', 'standalone mode off', 'give the glasses back to the pc']}}
# Questions and other requests: the general model answers them (or the PC does when it is there).
ASK = {'fr': ['quelle est la capitale de {x}', 'combien font {a} fois {b}', 'qui a ecrit {w}', 'raconte moi une blague',
              'quel temps fait il', 'c est quoi {t}', 'donne moi une idee de recette avec {f}', 'traduis {e} en anglais',
              'quelle heure est il a {c}', 'explique moi {t}', 'combien de pattes a {an}', 'qui est {p}',
              'pourquoi le ciel est bleu', 'ouvre youtube sur la tele', 'baisse le son de la tele', 'lance l aspirateur',
              'ou est mon telephone', 'rappelle moi de {r}', 'a quelle distance est la lune', 'suivant de quoi tu parles'],
       'en': ['what is the capital of {x}', 'what is {a} times {b}', 'who wrote {w}', 'tell me a joke',
              'what is the weather like', 'what is {t}', 'give me a recipe idea with {f}', 'translate {e} into french',
              'what time is it in {c}', 'explain {t}', 'how many legs does {an} have', 'who is {p}',
              'why is the sky blue', 'open youtube on the tv', 'turn the tv down', 'start the vacuum',
              'how far is the moon', 'remind me to {r}', 'next week what are you doing', 'what is the next train']}
# Orders for other devices (the PC's job, never the phone's): close in wording to the phone's own orders.
DEVICE = {'fr': ['monte le son', 'baisse le son de la tele', 'eteins la lumiere', 'allume la lumiere du salon',
                 'coupe le chauffage', 'mets la musique plus fort', 'eteins la tele', 'allume la tele', 'mets netflix',
                 'arrete l aspirateur', 'renvoie l aspirateur a sa base', 'baisse le volume', 'coupe le son',
                 'passe a la chaine suivante', 'ouvre le portail', 'ferme les volets', 'monte le chauffage'],
          'en': ['turn the volume up', 'turn the lights off', 'switch on the living room light', 'turn the heating off',
                 'make the music louder', 'turn off the tv', 'turn the tv on', 'put netflix on', 'stop the vacuum',
                 'send the vacuum home', 'lower the volume', 'mute the tv', 'next channel', 'open the gate',
                 'close the shutters', 'turn the heating up', 'turn down the music']}
FILL = {'x': ['france', 'italie', 'japon', 'canada', 'australie', 'bresil', 'kenya'],
        'a': ['7', '12', 'trois', 'neuf'], 'b': ['8', '15', 'six', 'onze'],
        'w': ['les miserables', 'hamlet', 'le petit prince', 'harry potter'],
        't': ['un trou noir', 'la photosynthese', 'le bitcoin', 'un volcan', 'l inflation'],
        'f': ['des oeufs', 'des pates', 'du riz', 'des tomates'], 'e': ['bonjour', 'merci beaucoup', 'a demain'],
        'c': ['tokyo', 'new york', 'londres', 'sydney'], 'an': ['une araignee', 'un chat', 'un insecte', 'une pieuvre'],
        'p': ['victor hugo', 'marie curie', 'ada lovelace'], 'r': ['acheter du pain', 'appeler maman', 'arroser les plantes']}
FILLERS = {'fr': ['', '', '', 'euh ', 'ok ', 'stp ', 'alors ', 'bon '], 'en': ['', '', '', 'uh ', 'ok ', 'please ', 'so ', 'hey ']}
TAILS = {'fr': ['', '', '', ' stp', ' s il te plait', ' merci', ' maintenant'], 'en': ['', '', '', ' please', ' thanks', ' now']}


def plain(s):
    s = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def fill(t, rnd):
    for k, vals in FILL.items():
        while '{' + k + '}' in t:
            t = t.replace('{' + k + '}', rnd.choice(vals), 1)
    return t


def templates():
    """(lang, template, reply, family) for every order."""
    out = []
    for v, words in NAV.items():
        for w in words:
            lang = 'en' if all(ord(c) < 128 for c in w) and any(x in w for x in ('next', 'open', 'select', 'enter', 'choose', 'back', 'go', 'previous', 'return', 'home', 'main', 'skip', 'move')) else 'fr'
            out.append((lang, w, {'a': 'nav', 'v': v}, 'nav'))
    for m, names in MODULE_WORDS.items():
        for lang in ('fr', 'en'):
            for t in ON[lang]:
                out.append((lang, (t, names[lang]), {'a': 'module', 'm': m, 'on': True}, 'module'))
            for t in OFF[lang]:
                out.append((lang, (t, names[lang]), {'a': 'module', 'm': m, 'on': False}, 'module'))
    for p, d in PROFILE.items():
        for lang, ts in d.items():
            out += [(lang, t, {'a': 'profile', 'p': p}, 'profile') for t in ts]
    for v, d in SPORT.items():
        for lang, ts in d.items():
            out += [(lang, t, {'a': 'sport', 'v': v}, 'sport') for t in ts]
    for v, d in LUMA.items():
        for lang, ts in d.items():
            out += [(lang, t, {'a': 'luma', 'v': v}, 'luma') for t in ts]
    for lang, ts in LUMA_SET.items():
        out += [(lang, t, {'a': 'luma', 'v': 'N'}, 'luma') for t in ts]
    for on, d in STANDALONE.items():
        for lang, ts in d.items():
            out += [(lang, t, {'a': 'standalone', 'on': on}, 'standalone') for t in ts]
    for lang, ts in ASK.items():
        out += [(lang, t, {'a': 'ask'}, 'ask') for t in ts]
    for lang, ts in DEVICE.items():
        out += [(lang, t, {'a': 'ask'}, 'device') for t in ts]
    return out


def expand(tpl, rnd, n):
    lang, t, reply, fam = tpl
    rows = []
    for _ in range(n):
        r = dict(reply)
        if isinstance(t, tuple):
            text = t[0].replace('{m}', rnd.choice(t[1]))
        else:
            text = t
        if r.get('v') == 'N':
            k = rnd.randint(0, 15)
            text = text.replace('{n}', str(k))
            r['v'] = k
        text = fill(text, rnd)
        text = (rnd.choice(FILLERS[lang]) + text + rnd.choice(TAILS[lang])).strip()
        if rnd.random() < 0.1:
            text = text.replace(' ', '  ', 1)
        rows.append({'prompt': plain(text), 'reply': r, 'lang': lang, 'family': fam})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--per-template', type=int, default=6)
    a = ap.parse_args(argv)
    rnd = random.Random(15)
    tpls = templates()
    rnd.shuffle(tpls)
    train, test = [], []
    for i, tpl in enumerate(tpls):
        (test if i % 6 == 0 else train).append(tpl)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    mult = {'device': 3, 'ask': 5, 'nav': 2, 'module': 0.5, 'luma': 1.5, 'sport': 1.5, 'standalone': 2, 'profile': 1.5}
    for name, tp, n in (('train', train, a.per_template), ('test', test, 2)):
        rows, seen = [], set()
        for t in tp:
            for r in expand(t, rnd, max(1, round(n * mult.get(t[3], 1)))):
                key = r['prompt']
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        rnd.shuffle(rows)
        with open(out / (name + '.jsonl'), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        fams = {}
        for r in rows:
            fams[r['family']] = fams.get(r['family'], 0) + 1
        print(name, len(rows), fams)
    (out / 'system.txt').write_text(SYSTEM, encoding='utf-8')


if __name__ == '__main__':
    main()
