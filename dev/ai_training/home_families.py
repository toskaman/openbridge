"""v3 (23 Nov 2026): every kind of home device, US English, UK English and French, and creating new features.

Each family is a list of (dialect, template). Dialects: en-US, en-GB, fr. Slots:
  {d}     a device of the family's kinds, optionally with a room ("the kitchen light", "la lampe du salon")
  {n}     a percentage, {t} a temperature, {trig}/{state}/{act}/{tgt} the parts of a "when X, then Y" link.
Gold targets use canonical English refs ("kitchen light", "bedroom heater"), whatever the request language, so the
model learns to understand the device, not to copy words.
"""
import random

ROOMS = [  # ref, en-US, en-GB, fr ("de la cuisine")
    ('kitchen', ['kitchen'], ['kitchen'], ['de la cuisine', 'dans la cuisine']),
    ('living room', ['living room', 'family room'], ['lounge', 'sitting room', 'front room'], ['du salon', 'dans le salon']),
    ('bedroom', ['bedroom'], ['bedroom'], ['de la chambre', 'dans la chambre']),
    ('office', ['office'], ['study', 'office'], ['du bureau', 'dans le bureau']),
    ('bathroom', ['bathroom', 'restroom'], ['bathroom', 'loo'], ['de la salle de bain', 'de la salle de bains']),
    ('hallway', ['hallway', 'hall'], ['hall', 'landing'], ['du couloir', "de l'entrée"]),
    ('kids room', ["kids' room", 'nursery'], ["kids' room", 'nursery'], ['de la chambre des enfants', 'de la chambre du petit']),
    ('dining room', ['dining room'], ['dining room'], ['de la salle à manger']),
    ('garden', ['backyard', 'yard'], ['garden'], ['du jardin', 'de la terrasse']),
]

# kind -> list of (ref, en-US names, en-GB names, fr names)
OBJECTS = {
    'light': [('light', ['light', 'lights'], ['light', 'lights'], ['la lumière', 'les lumières', 'la lumiere']),
              ('lamp', ['lamp', 'floor lamp'], ['lamp', 'standard lamp'], ['la lampe', 'le lampadaire']),
              ('ceiling light', ['ceiling light', 'overhead light'], ['big light', 'ceiling light'], ['le plafonnier', 'la lumière du plafond']),
              ('bedside lamp', ['nightstand lamp', 'bedside lamp'], ['bedside lamp'], ['la lampe de chevet']),
              ('led strip', ['LED strip', 'light strip'], ['LED strip'], ['le ruban LED', 'la bande LED']),
              ('string lights', ['string lights', 'Christmas lights'], ['fairy lights', 'Christmas lights'], ['la guirlande', 'la guirlande lumineuse'])],
    'appliance': [('plug', ['smart plug', 'plug', 'outlet'], ['smart plug', 'plug', 'socket'], ['la prise', 'la prise connectée']),
                  ('coffee machine', ['coffee maker', 'coffee machine'], ['coffee machine'], ['la machine à café', 'la cafetière']),
                  ('kettle', ['kettle', 'electric kettle'], ['kettle'], ['la bouilloire']),
                  ('fan', ['fan', 'ceiling fan'], ['fan'], ['le ventilateur', 'le ventilo']),
                  ('air purifier', ['air purifier'], ['air purifier'], ["le purificateur d'air"]),
                  ('dehumidifier', ['dehumidifier'], ['dehumidifier'], ['le déshumidificateur']),
                  ('washing machine', ['washer', 'washing machine'], ['washing machine'], ['la machine à laver', 'le lave-linge']),
                  ('dishwasher', ['dishwasher'], ['dishwasher'], ['le lave-vaisselle']),
                  ('towel rail', ['towel warmer'], ['heated towel rail'], ['le sèche-serviettes']),
                  ('electric blanket', ['electric blanket'], ['electric blanket'], ['la couverture chauffante'])],
    'thermostat': [('thermostat', ['thermostat'], ['thermostat'], ['le thermostat']),
                   ('heating', ['heat', 'heating'], ['heating', 'central heating'], ['le chauffage']),
                   ('heater', ['heater', 'radiator'], ['radiator', 'heater'], ['le radiateur']),
                   ('air conditioning', ['AC', 'air conditioning', 'A/C'], ['air con', 'air conditioning'], ['la clim', 'la climatisation'])],
    'speaker': [('speaker', ['speaker', 'music'], ['speaker', 'music'], ["l'enceinte", 'la musique']),
                ('sonos', ['Sonos'], ['Sonos'], ['la Sonos', "l'enceinte Sonos"]),
                ('soundbar', ['soundbar'], ['soundbar'], ['la barre de son']),
                ('stereo', ['stereo'], ['hi-fi', 'stereo'], ['la chaîne hi-fi', 'la chaîne']),
                ('smart speaker', ['Echo', 'HomePod', 'Google Home'], ['Echo', 'HomePod'], ["l'Echo", 'le HomePod', 'le Google Home'])],
    'cover': [('blinds', ['blinds', 'shades'], ['blinds', 'roller blind'], ['les stores', 'le store']),
              ('shutters', ['shutters', 'rolling shutters'], ['shutters'], ['les volets', 'le volet roulant', 'les volets roulants']),
              ('curtains', ['curtains', 'drapes'], ['curtains'], ['les rideaux'])],
    'lock': [('front door', ['front door', 'door'], ['front door', 'door'], ["la porte d'entrée", 'la porte']),
             ('back door', ['back door'], ['back door'], ['la porte de derrière', 'la porte du jardin'])],
}
ROOMLESS = {'lock', 'thermostat_whole'}

FR_ARTICLE_FIX = (('de le ', 'du '), ('de les ', 'des '), ('à le ', 'au '), ('à les ', 'aux '))


def fr_fix(t):
    for a, b in FR_ARTICLE_FIX:
        t = t.replace(a, b)
    return t


def pick_device(kind, dialect, rng, room_p=0.55):
    ref, us, gb, fr = rng.choice(OBJECTS[kind])
    room = None
    if kind != 'lock' and rng.random() < room_p:
        room = rng.choice(ROOMS if kind in ('light', 'speaker') else ROOMS[:-1])   # no "garden kettle"
    if dialect == 'fr':
        name = rng.choice(fr)
        if room:
            name = name + ' ' + rng.choice(room[3])
    else:
        name = rng.choice(us if dialect == 'en-US' else gb)
        if room:
            rn = rng.choice(room[1] if dialect == 'en-US' else room[2])
            name = ('the %s %s' % (rn, name)) if rng.random() < 0.6 else ('the %s in the %s' % (name, rn))
        else:
            name = 'the ' + name
    full_ref = ('%s %s' % (room[0], ref)) if room else ref
    return name, full_ref


def R(outcome, sid, targets, params=None, conf=0.9):
    return {'outcome': outcome, 'skill_id': sid, 'targets': targets, 'params': params or {}, 'confidence': conf,
            'ambiguities': [], 'clarifying_question': None}


def Q(outcome, question, amb):
    return {'outcome': outcome, 'skill_id': None, 'targets': [], 'params': {}, 'confidence': 0.0,
            'ambiguities': [amb], 'clarifying_question': question}


def U(outcome):
    return {'outcome': outcome, 'skill_id': None, 'targets': [], 'params': {}, 'confidence': 0.0,
            'ambiguities': [], 'clarifying_question': None}


DEVT = lambda ref: {'kind': 'device', 'ref': ref}
FABRIC = [{'kind': 'category', 'ref': 'fabric'}]

# family -> (skill_id or None, kinds for {d}, [(dialect, template)])
FAMILIES = {
    'home.turn_on': ('home.turn_on', ('light', 'appliance', 'speaker'), [
        ('en-US', 'Turn on {d}'), ('en-US', 'Turn {d} on'), ('en-US', 'Can you turn on {d}?'), ('en-US', 'Switch on {d}'),
        ('en-US', 'I need {d} on'), ('en-US', 'Power on {d}'), ('en-US', 'Get {d} going'), ('en-US', '{d} on please'),
        ('en-GB', 'Switch {d} on'), ('en-GB', 'Pop {d} on'), ('en-GB', 'Could you put {d} on?'), ('en-GB', 'Stick {d} on, cheers'),
        ('en-GB', 'Be a love and switch {d} on'), ('en-GB', 'Can you get {d} on for me?'),
        ('fr', 'Allume {d}'), ('fr', 'Tu peux allumer {d} ?'), ('fr', 'Mets {d} en marche'), ('fr', 'Démarre {d}'),
        ('fr', 'Active {d}'), ('fr', 'Allume-moi {d}'), ('fr', 'Faut allumer {d}'), ('fr', 'Branche {d}'),
        ('fr', 'Vas-y allume {d}'), ('fr', "J'aimerais que {d} soit allumée")]),
    'home.turn_off': ('home.turn_off', ('light', 'appliance', 'speaker'), [
        ('en-US', 'Turn off {d}'), ('en-US', 'Turn {d} off'), ('en-US', 'Shut off {d}'), ('en-US', 'Kill {d}'),
        ('en-US', 'Can you switch off {d}?'), ('en-US', 'Power down {d}'), ('en-US', '{d} off now'), ('en-US', 'Cut {d}'),
        ('en-GB', 'Switch {d} off'), ('en-GB', 'Knock {d} off'), ('en-GB', 'Could you turn {d} off, ta'), ('en-GB', 'Pop {d} off'),
        ('en-GB', "Switch {d} off, it's wasting electricity"), ('en-GB', 'Can you get {d} off?'),
        ('fr', 'Éteins {d}'), ('fr', 'Tu peux éteindre {d} ?'), ('fr', 'Coupe {d}'), ('fr', 'Arrête {d}'),
        ('fr', 'Désactive {d}'), ('fr', 'Éteins-moi {d}'), ('fr', 'Ferme {d}'), ('fr', 'Faut éteindre {d}'),
        ('fr', 'Stop {d}'), ('fr', 'Eteint {d} stp')]),
    'home.all_lights_off': ('home.turn_off', (), [
        ('en-US', 'Turn off all the lights'), ('en-US', 'Lights off everywhere'), ('en-US', 'Kill all the lights'),
        ('en-GB', 'Switch all the lights off'), ('en-GB', 'Every light off, please'),
        ('fr', 'Éteins toutes les lumières'), ('fr', 'Coupe toutes les lumières'), ('fr', 'Plus aucune lumière'),
        ('fr', 'Éteins tout l\'éclairage')]),
    'home.all_lights_on': ('home.turn_on', (), [
        ('en-US', 'Turn on all the lights'), ('en-US', 'All lights on'), ('en-GB', 'Switch every light on'),
        ('en-GB', 'Put all the lights on'), ('fr', 'Allume toutes les lumières'), ('fr', 'Allume tout l\'éclairage'),
        ('fr', 'Toutes les lumières allumées')]),
    'home.set_brightness': ('home.set_brightness', ('light',), [
        ('en-US', 'Dim {d} to {n}%'), ('en-US', 'Set {d} to {n} percent'), ('en-US', '{d} at {n}%'),
        ('en-US', 'Brightness {n} on {d}'), ('en-US', 'Make {d} {n} percent bright'), ('en-US', 'Turn {d} down to {n}%'),
        ('en-GB', 'Put {d} on {n} per cent'), ('en-GB', 'Bring {d} down to {n} per cent'), ('en-GB', 'Set {d} to {n}%, ta'),
        ('fr', 'Mets {d} à {n} %'), ('fr', 'Tamise {d} à {n}'), ('fr', 'Luminosité de {d} à {n} pour cent'),
        ('fr', 'Baisse {d} à {n} %'), ('fr', 'Règle {d} sur {n} pour cent'), ('fr', '{d} à {n} pourcent'),
        ('fr', 'Monte {d} à {n} %')]),
    'home.set_temperature': ('home.set_temperature', ('thermostat',), [
        ('en-US', 'Set {d} to {t} degrees'), ('en-US', 'Make it {t} degrees'), ('en-US', 'Turn {d} to {t}'),
        ('en-US', 'I want {t} degrees'), ('en-US', '{d} at {t} degrees please'), ('en-US', 'Change the temperature to {t}'),
        ('en-GB', 'Put {d} on {t} degrees'), ('en-GB', 'Whack {d} up to {t}'), ('en-GB', 'Can you set {d} to {t}, it\'s freezing'),
        ('en-GB', "Knock {d} down to {t}, it's boiling"),
        ('fr', 'Mets {d} à {t} degrés'), ('fr', 'Règle {d} sur {t}'), ('fr', 'Je veux {t} degrés'),
        ('fr', 'Passe {d} à {t} °C'), ('fr', 'Température à {t}'), ('fr', 'Monte {d} à {t} degrés, je me gèle'),
        ('fr', 'Baisse {d} à {t}, il fait trop chaud')]),
    'home.media_play': ('home.media_play', ('speaker',), [
        ('en-US', 'Play {d}'), ('en-US', 'Resume {d}'), ('en-US', 'Unpause {d}'), ('en-US', 'Start {d} again'),
        ('en-GB', 'Carry on playing {d}'), ('en-GB', 'Put {d} back on'),
        ('fr', 'Remets {d} en lecture'), ('fr', 'Reprends {d}'), ('fr', 'Relance {d}'), ('fr', 'Lecture sur {d}'),
        ('fr', 'Fais jouer {d}')]),
    'home.media_pause': ('home.media_pause', ('speaker',), [
        ('en-US', 'Pause {d}'), ('en-US', 'Hold {d}'), ('en-US', 'Stop {d} for a sec'), ('en-US', 'Pause the music'),
        ('en-GB', 'Pause {d} a mo'), ('en-GB', 'Hang on, pause {d}'),
        ('fr', 'Mets {d} en pause'), ('fr', 'Pause {d}'), ('fr', 'Stoppe {d} deux secondes'), ('fr', 'Mets la musique en pause'),
        ('fr', 'Coupe {d} un instant')]),
    'home.media_volume': ('home.media_volume', ('speaker',), [
        ('en-US', 'Set {d} volume to {n}'), ('en-US', 'Volume {n} on {d}'), ('en-US', '{d} volume at {n}'),
        ('en-GB', 'Put {d} on volume {n}'), ('en-GB', 'Turn {d} to {n}'),
        ('fr', 'Mets le volume de {d} à {n}'), ('fr', 'Volume de {d} à {n}'), ('fr', 'Règle {d} sur {n} de volume'),
        ('fr', 'Son de {d} à {n}')]),
    'home.cover_open': ('home.cover_open', ('cover',), [
        ('en-US', 'Open {d}'), ('en-US', 'Raise {d}'), ('en-US', 'Pull up {d}'), ('en-US', 'Let some light in, open {d}'),
        ('en-GB', 'Open {d}, please'), ('en-GB', 'Draw back {d}'),
        ('fr', 'Ouvre {d}'), ('fr', 'Remonte {d}'), ('fr', 'Lève {d}'), ('fr', 'Tu peux ouvrir {d} ?'), ('fr', 'Monte {d}')]),
    'home.cover_close': ('home.cover_close', ('cover',), [
        ('en-US', 'Close {d}'), ('en-US', 'Lower {d}'), ('en-US', 'Pull down {d}'), ('en-US', 'Shut {d}'),
        ('en-GB', 'Draw {d}'), ('en-GB', 'Close {d}, the sun is in my eyes'),
        ('fr', 'Ferme {d}'), ('fr', 'Descends {d}'), ('fr', 'Baisse {d}'), ('fr', 'Tu peux fermer {d} ?'), ('fr', 'Tire {d}')]),
    'home.lock': ('home.lock', ('lock',), [
        ('en-US', 'Lock {d}'), ('en-US', 'Lock up {d}'), ('en-US', 'Make sure {d} is locked'), ('en-US', 'Bolt {d}'),
        ('en-GB', 'Lock {d}, I\'m off to bed'), ('en-GB', 'Can you lock {d}?'),
        ('fr', 'Verrouille {d}'), ('fr', 'Ferme {d} à clé'), ('fr', 'Tu peux verrouiller {d} ?'), ('fr', 'Boucle {d}')]),
    'home.undo': ('home.undo', ('light', 'appliance', 'thermostat'), [
        ('en-US', 'Undo that on {d}'), ('en-US', 'Put {d} back how it was'), ('en-US', 'Revert {d}'),
        ('en-GB', 'Put {d} back as it was'), ('en-GB', 'Undo what you did to {d}'),
        ('fr', 'Annule pour {d}'), ('fr', 'Remets {d} comme avant'), ('fr', 'Reviens en arrière sur {d}')]),
    'create.suggest': ('create.suggest', (), [
        ('en-US', 'What new features could my devices do together?'), ('en-US', 'Suggest some automations'),
        ('en-US', 'Give me ideas for my smart home'), ('en-US', 'What could I automate?'),
        ('en-GB', 'Any clever ideas for my gadgets?'), ('en-GB', 'Suggest a few routines'),
        ('fr', "Propose-moi des idées d'automatisations"), ('fr', "Qu'est-ce que mes appareils pourraient faire ensemble ?"),
        ('fr', 'Donne-moi des idées de nouvelles fonctions'), ('fr', 'Invente des scénarios pour la maison'),
        ('fr', "Qu'est-ce que je pourrais automatiser ?")]),
    'learn.report': ('learn.report', (), [
        ('en-US', 'What have you learned about my devices?'), ('en-US', 'Which of my devices are reliable?'),
        ('en-US', 'Show me what works reliably'), ('en-GB', 'Which gadgets can I trust?'),
        ('en-GB', "What's dependable in the house?"),
        ('fr', "Qu'as-tu appris sur mes appareils ?"), ('fr', 'Quels appareils sont fiables ?'),
        ('fr', 'Montre-moi ce qui marche bien'), ('fr', 'Sur quels appareils je peux compter ?')]),
    'home.policy': (None, ('lock',), [
        ('en-US', 'Unlock {d}'), ('en-US', 'Open the garage'), ('en-US', 'Disarm the alarm'), ('en-US', 'Open the gate'),
        ('en-US', 'Turn off the security system'), ('en-GB', 'Let me in, unlock {d}'), ('en-GB', 'Open the garage door'),
        ('en-GB', 'Switch the burglar alarm off'),
        ('fr', 'Déverrouille {d}'), ('fr', 'Ouvre le garage'), ('fr', "Désactive l'alarme"), ('fr', 'Ouvre le portail'),
        ('fr', 'Ouvre la porte du garage'), ('fr', "Coupe l'alarme"), ('fr', 'Déverrouille la porte, j\'ai oublié mes clés')]),
    'home.clarify_device': (None, (), [
        ('en-US', 'Turn it on'), ('en-US', 'Switch it off'), ('en-US', 'Turn that off'), ('en-GB', 'Pop it on'),
        ('en-GB', 'Switch that off'), ('fr', 'Allume-le'), ('fr', 'Éteins ça'), ('fr', 'Allume'), ('fr', 'Coupe-le')]),
    'home.clarify_value': (None, ('light',), [
        ('en-US', 'Dim {d}'), ('en-US', 'Make {d} dimmer'), ('en-GB', 'Turn {d} down a bit'),
        ('fr', 'Tamise {d}'), ('fr', 'Baisse un peu {d}'), ('fr', 'Moins fort {d}')]),
    'home.unsupported': (None, (), [
        ('en-US', 'Order a pizza'), ('en-US', 'Call my mom'), ('en-US', "What's the weather tomorrow?"),
        ('en-US', 'Set an alarm for 7 am'), ('en-US', 'Tell me a joke'), ('en-US', 'Text my brother'),
        ('en-GB', 'Ring my mum'), ('en-GB', "What's on telly tonight?"), ('en-GB', 'Book a table at the pub'),
        ('en-GB', 'Put the bins out'),
        ('fr', 'Commande une pizza'), ('fr', 'Appelle ma mère'), ('fr', 'Quel temps fera-t-il demain ?'),
        ('fr', 'Mets un réveil à 7 h'), ('fr', 'Raconte-moi une blague'), ('fr', 'Envoie un SMS à mon frère'),
        ('fr', 'Sors les poubelles'), ('fr', 'Fais la vaisselle')]),
}

# "when X, then Y": triggers and actions with their phrasing per dialect
TRIGGERS = [  # ref, state, en phrases, fr phrases
    ('tv', 'playing', ['the TV starts playing', 'something starts playing on the TV', 'a movie starts on the TV'],
     ['la télé se met à jouer', 'un film commence sur la télé', 'la télé lance une lecture']),
    ('tv', 'paused', ['the TV is paused', 'I pause the TV'], ['la télé est en pause', 'je mets la télé en pause']),
    ('speaker', 'playing', ['the music starts', 'the speaker starts playing'], ["la musique démarre", "l'enceinte se met à jouer"]),
    ('front door', 'locked', ['the front door locks', 'I lock the front door'], ["la porte d'entrée se verrouille", "je verrouille la porte d'entrée"]),
    ('front door', 'unlocked', ['the front door is unlocked'], ["la porte d'entrée est déverrouillée"]),
    ('vacuum', 'cleaning', ['the vacuum starts cleaning', 'the robot starts'], ["l'aspirateur commence le ménage", 'le robot démarre']),
    ('vacuum', 'docked', ['the vacuum goes back to its dock', 'the robot is docked'], ["l'aspirateur retourne à sa base", 'le robot est sur sa base']),
    ('bedroom light', 'off', ['the bedroom light goes off', 'I switch the bedroom light off'], ['la lumière de la chambre s\'éteint']),
    ('living room light', 'on', ['the living room light comes on'], ['la lumière du salon s\'allume']),
    ('blinds', 'closed', ['the blinds close', 'the blinds are down'], ['les stores se ferment', 'les stores sont baissés']),
    ('heating', 'off', ['the heating turns off'], ['le chauffage s\'éteint']),
]
ACTIONS = [  # then_action, needs value, target kind, en verb, en-GB verb, fr verb
    ('turn_off', False, ('light', 'appliance'), ['turn off', 'switch off'], ['switch off', 'knock off'], ['éteins', 'coupe']),
    ('turn_on', False, ('light', 'appliance'), ['turn on', 'switch on'], ['switch on', 'put on'], ['allume', 'mets en marche']),
    ('set_brightness', True, ('light',), ['dim {tgt} to {n}%', 'set {tgt} to {n}% brightness'], ['dim {tgt} to {n} per cent'],
     ['mets {tgt} à {n} %', 'tamise {tgt} à {n} %']),
    ('pause', False, ('speaker',), ['pause'], ['pause'], ['mets en pause']),
    ('close', False, ('cover',), ['close', 'lower'], ['draw', 'close'], ['ferme', 'baisse']),
    ('open', False, ('cover',), ['open'], ['open'], ['ouvre']),
]
LINK_TEMPLATES = {
    'en-US': ['When {trig}, {act} {tgt}', 'Whenever {trig}, {act} {tgt}', 'Every time {trig}, {act} {tgt}',
              'Create an automation: when {trig}, {act} {tgt}', 'If {trig}, then {act} {tgt}', '{act} {tgt} whenever {trig}',
              'Can you make it so that when {trig}, you {act} {tgt}?'],
    'en-GB': ['When {trig}, {act} {tgt}', 'Each time {trig}, {act} {tgt}', 'Could you set it up so {trig} means you {act} {tgt}',
              'Make a routine: once {trig}, {act} {tgt}'],
    'fr': ['Quand {trig}, {act} {tgt}', 'Chaque fois que {trig}, {act} {tgt}', 'Dès que {trig}, {act} {tgt}',
           'Crée une automatisation : si {trig}, alors {act} {tgt}', 'Lorsque {trig}, {act} {tgt}',
           'Automatise ça : quand {trig}, {act} {tgt}', 'Fais en sorte que quand {trig}, tu {act} {tgt}'],
}


def gold(family, slots):
    sid, _, _ = FAMILIES[family] if family in FAMILIES else (None, None, None)
    if family == 'links.create':
        p = {'when_state': slots['state'], 'then_action': slots['act']}
        if 'n' in slots:
            p['value'] = slots['n']
        return R('when %s is %s, %s %s' % (slots['trig_ref'], slots['state'], slots['act'], slots['ref']), 'links.create',
                 [DEVT(slots['trig_ref']), DEVT(slots['ref'])], p, 0.85)
    if family in ('home.all_lights_off', 'home.all_lights_on'):
        return R('%s all lights' % ('switch off' if family.endswith('off') else 'switch on'), sid,
                 [{'kind': 'category', 'ref': 'light'}])
    if family in ('create.suggest', 'learn.report'):
        return R('suggest new features' if family == 'create.suggest' else 'report what was learned', sid, FABRIC)
    if family == 'home.policy':
        return U('refused by policy: OpenBridge never unlocks doors, moves garage doors or gates, or touches alarms')
    if family == 'home.unsupported':
        return U('no registered skill does this')
    if family == 'home.clarify_device':
        q = {'fr': 'Quel appareil ?'}.get(slots['lang'], 'Which device do you mean?')
        return Q('device not named', q, 'which device')
    if family == 'home.clarify_value':
        q = {'fr': 'À quel pourcentage ?'}.get(slots['lang'], 'To what brightness, in percent?')
        return Q('brightness value missing', q, 'which value')
    params = {}
    if 'n' in slots:
        params['value'] = slots['n']
    if 't' in slots:
        params['value'] = slots['t']
    return R('%s %s' % (sid.split('.', 1)[1].replace('_', ' '), slots['ref']), sid, [DEVT(slots['ref'])], params)


def render(family, dialect, template, rng):
    """One (text, slots) from a template, or None."""
    lang = 'fr' if dialect == 'fr' else 'en'
    slots = {'lang': lang, 'dialect': dialect}
    t = template
    if family == 'links.create':
        trig_ref, state, en_t, fr_t = rng.choice(TRIGGERS)
        act, needs, kinds, en_v, gb_v, fr_v = rng.choice(ACTIONS)
        name, ref = pick_device(rng.choice(kinds), dialect, rng, room_p=0.5)
        verb = rng.choice(fr_v if dialect == 'fr' else gb_v if dialect == 'en-GB' else en_v)
        if needs:
            slots['n'] = rng.choice([10, 15, 20, 25, 30, 40, 50])
            verb = verb.replace('{n}', str(slots['n']))
        if '{tgt}' not in verb:
            verb += ' {tgt}'
        t = t.replace('{trig}', rng.choice(fr_t if dialect == 'fr' else en_t)).replace('{act} {tgt}', verb).replace('{tgt}', name)
        slots.update(trig_ref=trig_ref, state=state, act=act, ref=ref)
        return (fr_fix(t) if dialect == 'fr' else t), slots
    _, kinds, _ = FAMILIES[family]
    if '{d}' in t:
        name, slots['ref'] = pick_device(rng.choice(kinds), dialect, rng)
        t = t.replace('{d}', name)
    if '{n}' in t:
        slots['n'] = rng.choice([rng.randrange(1, 101), rng.choice([10, 20, 25, 30, 40, 50, 60, 75, 80, 100])])
        t = t.replace('{n}', str(slots['n']))
    if '{t}' in t:
        slots['t'] = rng.choice([16, 17, 18, 18.5, 19, 19.5, 20, 20.5, 21, 21.5, 22, 23, 24, 25, 26])
        t = t.replace('{t}', ('%g' % slots['t']).replace('.', ',') if dialect == 'fr' and rng.random() < 0.7 else '%g' % slots['t'])
    if family == 'home.set_temperature' and 'ref' not in slots:
        slots['ref'] = 'thermostat'
    if family == 'home.media_pause' and 'ref' not in slots:
        slots['ref'] = 'speaker'
    if family == 'home.policy' and 'ref' not in slots:
        slots['ref'] = 'garage'
    t = t[0].upper() + t[1:]
    return (fr_fix(t) if dialect == 'fr' else t), slots


FAMILIES['links.create'] = ('links.create', (), [(d, t) for d, ts in LINK_TEMPLATES.items() for t in ts])


def build(vary, seed=11, k_train=8, k_test=3):
    rng = random.Random(seed)
    train, test = [], []
    for family, (_, _, templates) in FAMILIES.items():
        by_d = {}
        for d, t in templates:
            by_d.setdefault(d, []).append(t)
        for dialect, ts in by_d.items():
            ts = list(ts)
            rng.shuffle(ts)
            n_test = max(1, len(ts) // 5) if len(ts) >= 3 else 0
            kt = k_train * (2 if family == 'links.create' else 1) if not family.startswith(('home.unsupported', 'home.policy')) else 3
            for i, t in enumerate(ts):
                k = k_test if i < n_test else kt
                for _ in range(k):
                    text, slots = render(family, dialect, t, rng)
                    lang = slots['lang']
                    row = {'family': family, 'lang': lang, 'dialect': dialect, 'text': vary(text, lang, rng),
                           'reply': gold(family, slots)}
                    (test if i < n_test else train).append(row)
    return train, test


# Written by hand, never generated: real-sounding requests in all three dialects (test only).
def _s(sid, ref, params=None):
    return ('skill', sid, params or {}, ref)


HOME_NOVEL = [
    ('en-US', 'yo turn the kitchen lights on', _s('home.turn_on', 'kitchen light')),
    ('en-US', 'can u shut the coffee maker off', _s('home.turn_off', 'coffee machine')),
    ('en-US', 'bedroom lamp 30 percent', _s('home.set_brightness', 'bedroom lamp', {'value': 30})),
    ('en-US', 'its cold in here bump the thermostat to 22', _s('home.set_temperature', 'thermostat', {'value': 22})),
    ('en-US', 'pause the sonos real quick', _s('home.media_pause', 'sonos')),
    ('en-US', 'close the living room blinds', _s('home.cover_close', 'living room blinds')),
    ('en-US', 'lock the back door', _s('home.lock', 'back door')),
    ('en-US', 'whenever the vacuum starts, pause the speaker', ('link', ['vacuum', 'speaker'], {'when_state': 'cleaning', 'then_action': 'pause'})),
    ('en-US', 'any ideas what my devices could do together', _s('create.suggest', 'fabric')),
    ('en-US', 'unlock the front door for the dog walker', ('unsupported',)),
    ('en-US', 'turn it off', ('clarify',)),
    ('en-GB', 'pop the kettle on would you', _s('home.turn_on', 'kettle')),
    ('en-GB', 'switch the big light off in the lounge', _s('home.turn_off', 'living room ceiling light')),
    ('en-GB', "put the heating on 21, it's nippy", _s('home.set_temperature', 'heating', {'value': 21})),
    ('en-GB', 'draw the curtains in the bedroom', _s('home.cover_close', 'bedroom curtains')),
    ('en-GB', 'knock the fairy lights off', _s('home.turn_off', 'string lights')),
    ('en-GB', 'turn the telly down', _s('tv_volume_step', 'tv', {'direction': 'down'})),
    ('en-GB', 'get the hoover going', _s('vacuum.start', 'vacuum')),
    ('en-GB', 'which of my gadgets actually work properly', _s('learn.report', 'fabric')),
    ('en-GB', 'switch the burglar alarm off', ('unsupported',)),
    ('en-GB', 'ring my nan', ('unsupported',)),
    ('fr', 'allume la lumiere de la cuisine stp', _s('home.turn_on', 'kitchen light')),
    ('fr', 'eteins la clim du bureau', _s('home.turn_off', 'office air conditioning')),
    ('fr', 'mets le salon à 20 degrés', _s('home.set_temperature', 'living room thermostat', {'value': 20})),
    ('fr', 'baisse la lampe de chevet a 15 %', _s('home.set_brightness', 'bedside lamp', {'value': 15})),
    ('fr', 'ferme les volets de la chambre', _s('home.cover_close', 'bedroom shutters')),
    ('fr', 'ouvre les stores du salon', _s('home.cover_open', 'living room blinds')),
    ('fr', 'mets la musique en pause', _s('home.media_pause', 'speaker')),
    ('fr', 'verrouille la porte d entrée', _s('home.lock', 'front door')),
    ('fr', "quand l'aspirateur démarre, mets l'enceinte en pause", ('link', ['vacuum', 'speaker'], {'when_state': 'cleaning', 'then_action': 'pause'})),
    ('en-GB', 'when the telly starts playing, dim the lounge lamp to 20 per cent', ('link', ['tv', 'living room lamp'], {'when_state': 'playing', 'then_action': 'set_brightness', 'value': 20})),
    ('fr', 'dès que je verrouille la porte d entrée éteins toutes les prises', ('link', ['front door', 'plug'], {'when_state': 'locked', 'then_action': 'turn_off'})),
    ('fr', 'propose moi des trucs à automatiser', _s('create.suggest', 'fabric')),
    ('fr', 'ouvre le portail', ('unsupported',)),
    ('fr', 'allume', ('clarify',)),
    ('fr', 'commande des croissants', ('unsupported',)),
]
