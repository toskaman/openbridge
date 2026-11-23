"""Independent OpenBridge command test set (French + English), written by hand.

These requests were written BEFORE the v2 training templates and are never used for training: make_dataset.py
drops any training sentence that is a near-duplicate of one of them. They imitate real people: spoken French,
slang, missing accents, typos, number words, indirect phrasing, extra words. This is the set that tells us whether
the model generalises, rather than whether it remembers our templates.

Each row: (lang, text, expected) where expected is one of
  ('skill', skill_id, params, target_ref)
  ('clarify',)       the router must ask a question (needs_clarification)
  ('unsupported',)   nothing OpenBridge can or may do (unsupported)
"""

YT, NF, PV, DP = ('com.google.android.youtube.tv', 'com.netflix.ninja', 'com.amazon.amazonvideo.livingroom',
                  'com.disney.disneyplus')
SP, TW, PX, VLC, KO, CA = ('com.spotify.tv.android', 'tv.twitch.android.app', 'com.plexapp.android',
                           'org.videolan.vlc', 'org.xbmc.kodi', 'com.canal.android.canal')


def S(skill, params=None, ref=None):
    return ('skill', skill, params or {}, ref)


C, U = ('clarify',), ('unsupported',)
VS, VP, VD, VK, VE = (S('vacuum.start', ref='vacuum'), S('vacuum.pause', ref='vacuum'), S('vacuum.dock', ref='vacuum'),
                      S('vacuum.seek', ref='vacuum'), S('vacuum.empty_dust', ref='vacuum'))
UP, DOWN = S('tv_volume_step', {'direction': 'up'}, 'tv'), S('tv_volume_step', {'direction': 'down'}, 'tv')


def VOL(n):
    return S('tv_volume_set', {'value': n}, 'tv')


def APP(p):
    return S('app_launch', {'package': p}, 'tv')


def FACTS(ref):
    return S('device_facts', ref=ref)


FABRIC = S('fabric.status', ref='fabric')
BLE = S('ble_scan_room', ref='relay')


def BLES(n):
    return S('ble_scan_room', {'seconds': n}, 'relay')


NOVEL = [
    # ---- vacuum.start
    ('fr', "bon allez l'aspi au boulot", VS), ('fr', 'tu peux faire le ménage avec le robot stp', VS),
    ('fr', 'lance le robot aspirateur maintenant', VS), ('fr', "c'est sale ici, envoie l'aspirateur", VS),
    ('fr', 'demarre l aspirateur', VS), ('fr', 'go le robot, nettoyage', VS),
    ('fr', 'faut passer l aspi dans le salon', VS), ('fr', 'nettoie la maison avec le robot', VS),
    ('fr', 'mets en route le robot', VS), ('fr', 'active l aspirateur', VS),
    ('en', 'kick off a cleaning run', VS), ('en', 'the floor is dirty, send the robot out', VS),
    ('en', 'start the hoover pls', VS), ('en', 'begin vacuuming', VS), ('en', 'robot vacuum go', VS),
    ('en', 'can the vacuum do a round now', VS), ('en', 'fire up the robot vacuum', VS),
    # ---- vacuum.pause
    ('fr', 'pause le robot', VP), ('fr', "attends, arrête l'aspi deux secondes", VP),
    ('fr', 'mets le ménage en pause', VP), ('fr', 'le robot fait trop de bruit, mets le en pause', VP),
    ('fr', 'stop le robot un moment, je téléphone', VP), ('fr', "suspend l'aspirateur", VP),
    ('fr', 'interromps le nettoyage', VP), ('fr', 'met en pose l aspirateur', VP),
    ('en', 'hold the vacuum for a sec', VP), ('en', "i'm on a call, pause the robot", VP),
    ('en', 'pause cleaning', VP), ('en', 'stop the vacuum for now, keep it where it is', VP),
    ('en', 'suspend the cleaning run', VP), ('en', 'halt the robot a moment', VP),
    # ---- vacuum.dock
    ('fr', 'renvoie le robot à la maison', VD), ('fr', "l'aspi rentre à sa base", VD),
    ('fr', 'fais rentrer le robot', VD), ('fr', 'le robot doit aller se recharger', VD),
    ('fr', "remet l'aspirateur sur son socle", VD), ('fr', 'retour à la base pour le robot', VD),
    ('fr', 'c est fini le ménage, range l aspi', VD), ('fr', 'renvoi l aspirateur a la station', VD),
    ('en', 'robot go home', VD), ('en', 'park the vacuum on its dock', VD),
    ('en', 'the vacuum should go recharge', VD), ('en', 'call the robot back to base', VD),
    ('en', 'done cleaning, send it back to the charger', VD), ('en', 'return to dock vacuum', VD),
    # ---- vacuum.seek
    ('fr', 'il est où le robot', VK), ('fr', "je retrouve plus l'aspirateur", VK),
    ('fr', 'fais sonner le robot', VK), ('fr', "aide moi à trouver l'aspi", VK),
    ('fr', 'le robot est coincé quelque part, fais le biper', VK), ('fr', 'repère le robot aspirateur', VK),
    ('fr', 'ou se cache l aspirateur', VK),
    ('en', "where did the robot go", VK), ('en', 'beep the vacuum so i can find it', VK),
    ('en', 'the vacuum is stuck somewhere, find it', VK), ('en', 'ping the robot vacuum', VK),
    ('en', 'help me locate my hoover', VK),
    # ---- vacuum.empty_dust
    ('fr', "vide le réservoir de l'aspi", VE), ('fr', 'le bac du robot est plein, vide le', VE),
    ('fr', 'lance la vidange du bac à poussière', VE), ('fr', 'vider la poussiere du robot', VE),
    ('en', 'the vacuum bin is full, empty it', VE), ('en', 'auto-empty the robot', VE),
    ('en', 'dump the dust from the robot vacuum', VE), ('en', 'empty the vacuum', VE),
    # ---- tv_volume_set
    ('fr', 'mets la télé à 30', VOL(30)), ('fr', 'le son de la tv à vingt', VOL(20)),
    ('fr', 'volume de la télé sur 12', VOL(12)), ('fr', 'règle la télé à 45 de volume', VOL(45)),
    ('fr', 'son télé 8', VOL(8)), ('fr', 'mets le volume à 0 sur la télé', VOL(0)),
    ('fr', 'je veux le volume de la tele a 60', VOL(60)), ('fr', 'passe le son de la télévision à quinze', VOL(15)),
    ('en', 'tv to 35', VOL(35)), ('en', 'set the telly to volume ten', VOL(10)),
    ('en', 'make the tv volume 22', VOL(22)), ('en', 'television volume at 50 please', VOL(50)),
    ('en', 'put the tv sound on 18', VOL(18)), ('en', 'mute level, volume 0 on the tv', VOL(0)),
    # ---- tv_volume_step up / down (device named)
    ('fr', 'monte un peu la télé', UP), ('fr', "j'entends rien, monte le son de la télé", UP),
    ('fr', 'augmente la télé', UP), ('fr', 'la tv plus fort stp', UP), ('fr', 'monte le volume de la tv', UP),
    ('fr', 'un cran de plus sur la télé', UP), ('fr', 'remonte le son de la télévision', UP),
    ('en', 'turn the tv up a little', UP), ('en', "can't hear the tv, louder", UP),
    ('en', 'bump the tv volume up', UP), ('en', 'tv volume one notch up', UP), ('en', 'increase the tv sound', UP),
    ('fr', 'baisse un peu la télé', DOWN), ('fr', 'la télé est trop forte', DOWN),
    ('fr', 'moins fort la tv', DOWN), ('fr', 'diminue le son de la télévision', DOWN),
    ('fr', 'un cran de moins sur la télé', DOWN), ('fr', 'baisse le volume de la tele stp', DOWN),
    ('en', 'turn the tv down a bit', DOWN), ('en', 'the tv is way too loud', DOWN),
    ('en', 'lower the telly', DOWN), ('en', 'tv volume down one step', DOWN), ('en', 'quieter on the television', DOWN),
    # ---- app_launch
    ('fr', 'mets youtube', APP(YT)), ('fr', 'lance netflix sur la télé', APP(NF)),
    ('fr', 'je veux regarder un truc sur disney plus', APP(DP)), ('fr', 'ouvre prime video', APP(PV)),
    ('fr', 'mets spotify sur la tv', APP(SP)), ('fr', 'lance twitch', APP(TW)), ('fr', 'ouvre plex sur la télé', APP(PX)),
    ('fr', 'démarre vlc', APP(VLC)), ('fr', 'lance kodi sur la tele', APP(KO)), ('fr', 'mets mycanal', APP(CA)),
    ('en', 'fire up youtube on the tv', APP(YT)), ('en', 'netflix please', APP(NF)),
    ('en', 'open disney+ on the television', APP(DP)), ('en', 'i wanna watch something on prime video', APP(PV)),
    ('en', 'spotify on the tv', APP(SP)), ('en', 'launch plex', APP(PX)), ('en', 'start kodi', APP(KO)),
    ('en', 'put twitch on', APP(TW)),
    # ---- device_facts
    ('fr', 'donne moi les infos de la télé', FACTS('tv')), ('fr', 'qu est ce que tu sais sur ma montre', FACTS('watch')),
    ('fr', 'infos sur mon téléphone', FACTS('phone')), ('fr', 'détails de la box', FACTS('router')),
    ('fr', 'montre moi l état de mon pc', FACTS('computer')), ('fr', "les caractéristiques de l'aspirateur", FACTS('vacuum')),
    ('en', 'tell me about my phone', FACTS('phone')), ('en', 'details on the watch', FACTS('watch')),
    ('en', 'what are the specs of the tv', FACTS('tv')), ('en', 'info about the router', FACTS('router')),
    ('en', 'show my computer facts', FACTS('computer')),
    # ---- fabric.status
    ('fr', 'combien d appareils sont connectés là', FABRIC), ('fr', 'résumé de mes appareils', FABRIC),
    ('fr', "c'est quoi l'état de mes appareils", FABRIC), ('fr', 'qui est en ligne', FABRIC),
    ('fr', 'fais le point sur mes appareils', FABRIC),
    ('en', 'how many gadgets are connected', FABRIC), ('en', 'device overview please', FABRIC),
    ('en', "what's connected right now", FABRIC), ('en', 'give me the status of everything', FABRIC),
    # ---- ble_scan_room
    ('fr', 'cherche du bluetooth autour', BLE), ('fr', 'quels objets bluetooth il y a près de moi', BLE),
    ('fr', 'lance une recherche bluetooth', BLE), ('fr', 'scan ble pendant 10 secondes', BLES(10)),
    ('fr', 'scanne le bluetooth 5 secondes', BLES(5)),
    ('en', 'look for bluetooth devices nearby', BLE), ('en', 'ble scan', BLE),
    ('en', 'scan bluetooth for 8 seconds', BLES(8)), ('en', 'anything with bluetooth around here?', BLE),
    # ---- clarify: volume without a device, conflicting vacuum, app not named
    ('fr', 'plus fort', C), ('fr', 'monte', C), ('fr', 'change le son', C), ('fr', 'le son', C),
    ('fr', 'un peu plus de volume', C), ('fr', 'remonte', C),
    ('en', 'louder', C), ('en', 'turn it up', C), ('en', 'volume', C), ('en', 'more volume', C),
    ('fr', 'démarre et arrête l aspirateur', C), ('fr', "fais quelque chose avec l'aspi", C),
    ('en', 'start and pause the vacuum', C), ('en', 'do the vacuum thing', C),
    ('fr', 'ouvre une appli', C), ('fr', 'mets un truc sur la télé', C), ('fr', 'lance une app de films', C),
    ('en', 'open an app on the tv', C), ('en', 'put something on to watch', C), ('en', 'launch a streaming app', C),
    # ---- unsupported (out of scope, or forbidden by policy)
    ('fr', 'déverrouille la porte', U), ('fr', 'ouvre le portail', U), ('fr', "coupe l'alarme", U),
    ('fr', 'montre moi la caméra du salon', U), ('fr', 'qui est à la maison', U),
    ('fr', 'commande des courses', U), ('fr', 'appelle papa', U), ('fr', 'quelle heure il est à tokyo', U),
    ('fr', 'écris un poème', U), ('fr', 'mets de la musique classique', U), ('fr', 'éteins le four', U),
    ('fr', 'achète un nouvel aspirateur', U), ('fr', 'réserve un restaurant', U), ('fr', 'change le mot de passe de la box', U),
    ('en', 'unlock the back door', U), ('en', 'open the garage', U), ('en', 'turn off the alarm system', U),
    ('en', 'show me the front camera', U), ('en', 'who is home right now', U), ('en', 'order groceries', U),
    ('en', 'call my brother', U), ('en', 'what is the capital of peru', U), ('en', 'write a song', U),
    ('en', 'book a taxi', U), ('en', 'reset the router password', U), ('en', 'buy a new tv', U),
]
