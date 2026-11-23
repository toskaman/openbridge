"""Build the OpenBridge command-understanding dataset (French + English).

Each example is exactly what the local model sees in production: the prompt from
src.runtime.nl_router.build_prompt(text, lang), and the gold JSON reply. Gold replies follow the router's
contract: one registered skill_id with targets and params, or skill_id null with a clarifying question
(ambiguous), or skill_id null with confidence 0 (not something OpenBridge can do).

Leakage guard: every family's phrasings are split by template BEFORE expansion, so no test sentence shares
a template with training; the test set also adds hand-written requests that no template produces.

v2 (23 Nov 2026): EXTRA templates per family (spoken French, slang, indirect phrasing), app-name aliases, number
words, more voice-style noise. A separate, independent set written by hand (novel_test.py, written before these
templates) is exported as novel.jsonl; any template that can produce a near-duplicate of one of its lines is
dropped from training entirely, so novel.jsonl measures generalisation, not memory.

    python dev/ai_training/make_dataset.py --out E:/OpenBridgeAI/data_v2
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.runtime.nl_router import build_prompt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from novel_test import NOVEL  # noqa: E402

TV = {'en': ['the TV', 'the television', 'the living room TV', 'the telly', 'TV'],
      'fr': ['la télé', 'la TV', 'la télévision', 'la télé du salon', 'le téléviseur']}
VAC = {'en': ['the vacuum', 'the robot vacuum', 'the robot', 'my vacuum', 'the hoover'],
       'fr': ["l'aspirateur", 'le robot aspirateur', 'le robot', 'mon aspirateur', "l'aspi"]}
APPS = {'YouTube': 'com.google.android.youtube.tv', 'Netflix': 'com.netflix.ninja',
        'Prime Video': 'com.amazon.amazonvideo.livingroom', 'Disney+': 'com.disney.disneyplus',
        'Spotify': 'com.spotify.tv.android', 'Twitch': 'tv.twitch.android.app', 'Plex': 'com.plexapp.android',
        'VLC': 'org.videolan.vlc', 'Kodi': 'org.xbmc.kodi', 'myCANAL': 'com.canal.android.canal'}
APP_ALIASES = {'YouTube': ['YouTube', 'youtube', 'Youtube'], 'Netflix': ['Netflix', 'netflix'],
               'Prime Video': ['Prime Video', 'Amazon Prime', 'Prime', 'prime video'],
               'Disney+': ['Disney+', 'Disney Plus', 'disney'], 'Spotify': ['Spotify', 'spotify'],
               'Twitch': ['Twitch', 'twitch'], 'Plex': ['Plex', 'plex'], 'VLC': ['VLC', 'vlc'], 'Kodi': ['Kodi', 'kodi'],
               'myCANAL': ['myCANAL', 'Canal+', 'canal plus', 'MyCanal']}
NUM_WORDS = {'en': {0: 'zero', 5: 'five', 10: 'ten', 12: 'twelve', 15: 'fifteen', 20: 'twenty', 25: 'twenty-five',
                    30: 'thirty', 40: 'forty', 50: 'fifty', 60: 'sixty', 70: 'seventy', 80: 'eighty'},
             'fr': {0: 'zéro', 5: 'cinq', 10: 'dix', 12: 'douze', 15: 'quinze', 20: 'vingt', 25: 'vingt-cinq',
                    30: 'trente', 40: 'quarante', 50: 'cinquante', 60: 'soixante', 70: 'soixante-dix', 80: 'quatre-vingts'}}
DEVICES = {'en': [('the TV', 'tv'), ('my phone', 'phone'), ('the watch', 'watch'), ('the vacuum', 'vacuum'),
                  ('the router', 'router'), ('my PC', 'computer')],
           'fr': [('la télé', 'tv'), ('mon téléphone', 'phone'), ('la montre', 'watch'), ("l'aspirateur", 'vacuum'),
                  ('la box', 'router'), ('mon PC', 'computer')]}


def reply(outcome, skill_id, targets, params=None, conf=0.9):
    return {'outcome': outcome, 'skill_id': skill_id, 'targets': targets, 'params': params or {},
            'confidence': conf, 'ambiguities': [], 'clarifying_question': None}


def clarify(outcome, question, ambiguity):
    return {'outcome': outcome, 'skill_id': None, 'targets': [], 'params': {}, 'confidence': 0.0,
            'ambiguities': [ambiguity], 'clarifying_question': question}


def unsupported(outcome):
    return {'outcome': outcome, 'skill_id': None, 'targets': [], 'params': {}, 'confidence': 0.0,
            'ambiguities': [], 'clarifying_question': None}


DEV = lambda ref: [{'kind': 'device', 'ref': ref}]

# family -> list of (lang, template, builder). Templates use {tv} {vac} {n} {app} {dev} {s}.
FAMILIES = {
    'vacuum.start': [
        ('en', 'Start {vac}', None), ('en', 'Start cleaning', None), ('en', 'Can you start {vac}?', None),
        ('en', 'Run {vac} now', None), ('en', 'Vacuum the house', None), ('en', 'Launch a cleaning with {vac}', None),
        ('en', 'Get {vac} going', None), ('en', 'Time to clean, start {vac}', None),
        ('fr', 'Lance {vac}', None), ('fr', 'Démarre {vac}', None), ('fr', 'Lance le ménage', None),
        ('fr', 'Tu peux lancer {vac} ?', None), ('fr', 'Passe l\'aspirateur', None), ('fr', 'Mets {vac} en marche', None),
        ('fr', 'Allez, on nettoie, démarre {vac}', None), ('fr', 'Fais tourner {vac}', None)],
    'vacuum.pause': [
        ('en', 'Pause {vac}', None), ('en', 'Stop {vac} for a moment', None), ('en', 'Hold on, pause the cleaning', None),
        ('en', 'Can you pause {vac}?', None), ('en', 'Freeze {vac} where it is', None), ('en', 'Put {vac} on pause', None),
        ('fr', 'Mets {vac} en pause', None), ('fr', 'Pause {vac}', None), ('fr', 'Arrête {vac} un instant', None),
        ('fr', 'Stoppe le ménage deux secondes', None), ('fr', 'Tu peux mettre {vac} en pause ?', None),
        ('fr', 'Fige {vac} là où il est', None)],
    'vacuum.dock': [
        ('en', 'Send {vac} home', None), ('en', 'Dock {vac}', None), ('en', 'Send {vac} back to its base', None),
        ('en', '{vac} go charge', None), ('en', 'Return {vac} to the dock', None), ('en', 'Put {vac} back on its charger', None),
        ('fr', 'Renvoie {vac} à sa base', None), ('fr', 'Remets {vac} à la base', None), ('fr', 'Va recharger {vac}', None),
        ('fr', '{vac} retourne à la base', None), ('fr', 'Range {vac}', None), ('fr', 'Ramène {vac} sur son chargeur', None)],
    'vacuum.seek': [
        ('en', 'Where is {vac}?', None), ('en', 'Find {vac}', None), ('en', 'Make {vac} beep', None),
        ('en', 'I lost {vac}, help me find it', None), ('en', 'Locate {vac}', None),
        ('fr', 'Où est {vac} ?', None), ('fr', 'Trouve {vac}', None), ('fr', 'Fais biper {vac}', None),
        ('fr', "J'ai perdu {vac}", None), ('fr', 'Localise {vac}', None)],
    'vacuum.empty_dust': [
        ('en', 'Empty the dustbin of {vac}', None), ('en', 'Empty the dust', None), ('en', 'Have {vac} empty its bin', None),
        ('en', 'Clear the dust from {vac}', None),
        ('fr', 'Vide le bac de {vac}', None), ('fr', 'Vide la poussière', None), ('fr', 'Fais vider le bac à poussière', None),
        ('fr', 'Vidange {vac}', None)],
    'tv_volume_set': [
        ('en', 'Set {tv} volume to {n}', None), ('en', 'Volume {n} on {tv}', None), ('en', 'Put the volume at {n}', None),
        ('en', 'Change {tv} volume to {n}', None), ('en', 'Make the TV volume exactly {n}', None), ('en', 'Sound to {n} please', None),
        ('fr', 'Mets le volume de {tv} à {n}', None), ('fr', 'Volume à {n}', None), ('fr', 'Règle le son de {tv} sur {n}', None),
        ('fr', 'Passe le volume à {n}', None), ('fr', 'Son à {n} sur {tv}', None), ('fr', 'Volume {n} sur {tv} stp', None)],
    'tv_volume_step_up': [
        ('en', 'Turn {tv} up', None), ('en', 'Volume up on {tv}', None), ('en', 'A bit louder on {tv}', None),
        ('en', 'Raise the volume of {tv}', None), ('en', 'Louder on {tv} please', None),
        ('fr', 'Monte le son de {tv}', None), ('fr', 'Plus fort sur {tv}', None), ('fr', 'Augmente le volume de {tv}', None),
        ('fr', 'Un peu plus fort {tv}', None), ('fr', 'Volume plus sur {tv}', None)],
    'tv_volume_step_down': [
        ('en', 'Turn {tv} down', None), ('en', 'Volume down on {tv}', None), ('en', 'A bit quieter on {tv}', None),
        ('en', 'Lower the volume of {tv}', None), ('en', 'Softer on {tv} please', None),
        ('fr', 'Baisse le son de {tv}', None), ('fr', 'Moins fort sur {tv}', None), ('fr', 'Diminue le volume de {tv}', None),
        ('fr', 'Un peu moins fort {tv}', None), ('fr', 'Volume moins sur {tv}', None)],
    'app_launch': [
        ('en', 'Open {app} on {tv}', None), ('en', 'Launch {app}', None), ('en', 'Put {app} on {tv}', None),
        ('en', 'Start {app} on the TV', None), ('en', 'I want to watch {app}', None), ('en', 'Can you open {app} on {tv}?', None),
        ('fr', 'Ouvre {app} sur {tv}', None), ('fr', 'Lance {app}', None), ('fr', 'Mets {app} sur {tv}', None),
        ('fr', 'Démarre {app} sur la télé', None), ('fr', 'Je veux regarder {app}', None), ('fr', 'Tu peux ouvrir {app} ?', None)],
    'ble_scan_room': [
        ('en', 'Scan for bluetooth devices', None), ('en', 'What bluetooth devices are around?', None),
        ('en', 'Look for nearby BLE devices', None), ('en', 'Scan the room for bluetooth for {s} seconds', 'seconds'),
        ('en', 'Find bluetooth gadgets nearby', None), ('en', 'Run a bluetooth scan', None),
        ('fr', 'Scanne les appareils bluetooth', None), ('fr', 'Quels appareils bluetooth sont autour ?', None),
        ('fr', 'Cherche les appareils BLE à proximité', None), ('fr', 'Scan bluetooth pendant {s} secondes', 'seconds'),
        ('fr', 'Trouve les objets bluetooth proches', None), ('fr', 'Lance un scan bluetooth', None)],
    'device_facts': [
        ('en', 'Show me the info of {dev}', None), ('en', 'What do you know about {dev}?', None), ('en', 'Give me the facts for {dev}', None),
        ('en', 'Read the details of {dev}', None), ('en', 'Status of {dev}', None),
        ('fr', 'Montre-moi les infos de {dev}', None), ('fr', 'Que sais-tu de {dev} ?', None), ('fr', 'Donne-moi les détails de {dev}', None),
        ('fr', "Lis les informations de {dev}", None), ('fr', 'État de {dev}', None)],
    'fabric.status': [
        ('en', 'How many devices are online?', None), ('en', 'Give me a summary of my devices', None), ('en', 'How many devices do I have?', None),
        ('en', 'Overview of the fabric', None), ('en', 'Count my connected devices', None), ('en', "What's online right now?", None),
        ('fr', 'Combien d\'appareils sont en ligne ?', None), ('fr', 'Fais-moi un résumé de mes appareils', None),
        ('fr', "Combien j'ai d'appareils ?", None), ('fr', 'État général des appareils', None), ('fr', 'Compte mes appareils connectés', None),
        ('fr', "Qu'est-ce qui est en ligne là ?", None)],
    'clarify_volume': [
        ('en', 'Turn it up', None), ('en', 'Louder', None), ('en', 'Change the volume', None), ('en', 'Volume', None),
        ('fr', 'Monte le son', None), ('fr', 'Plus fort', None), ('fr', 'Change le volume', None), ('fr', 'Le volume', None)],
    'clarify_vacuum': [
        ('en', 'Turn the vacuum on and off', None), ('en', 'Start and stop the robot', None), ('en', 'Do something with the vacuum', None),
        ('fr', "Allume et éteins l'aspirateur", None), ('fr', 'Démarre et arrête le robot', None), ('fr', "Fais un truc avec l'aspirateur", None)],
    'clarify_app': [
        ('en', 'Open an app on the TV', None), ('en', 'Launch something to watch', None), ('en', 'Put a streaming app on', None),
        ('fr', 'Ouvre une appli sur la télé', None), ('fr', 'Lance un truc à regarder', None), ('fr', 'Mets une appli de streaming', None)],
    'unsupported': [
        ('en', 'Book me a flight to Paris', None), ('en', "What's the weather tomorrow?", None), ('en', 'Send a WhatsApp to Julie', None),
        ('en', 'Call my mother', None), ('en', 'Order a pizza', None), ('en', 'Write an email to my boss', None),
        ('en', 'Unlock the front door', None), ('en', 'Change my wifi password', None), ('en', 'Play some jazz', None),
        ('en', 'Tell me a joke', None), ('en', 'Set an alarm for 7am', None), ('en', 'Buy more coffee', None),
        ('en', 'Translate this into Spanish', None), ('en', 'Delete all my photos', None), ('en', 'Turn off the oven', None),
        ('en', 'Disarm the alarm', None),
        ('fr', 'Réserve-moi un vol pour Paris', None), ('fr', 'Quel temps fera-t-il demain ?', None), ('fr', 'Envoie un WhatsApp à Julie', None),
        ('fr', 'Appelle ma mère', None), ('fr', 'Commande une pizza', None), ('fr', 'Écris un mail à mon patron', None),
        ('fr', "Déverrouille la porte d'entrée", None), ('fr', 'Change le mot de passe wifi', None), ('fr', 'Mets du jazz', None),
        ('fr', 'Raconte-moi une blague', None), ('fr', 'Mets un réveil à 7h', None), ('fr', 'Achète du café', None),
        ('fr', 'Traduis ça en espagnol', None), ('fr', 'Supprime toutes mes photos', None), ('fr', 'Éteins le four', None),
        ('fr', "Désactive l'alarme", None)],
}


# v2 extra templates: written after novel_test.py; any template that can echo a novel line is dropped (see build()).
EXTRA = {
    'vacuum.start': [
        ('en', 'Clean the floor with {vac}', None), ('en', 'Send {vac} out to clean', None), ('en', 'Begin a cleaning cycle', None),
        ('en', '{vac}, start cleaning', None), ('en', 'Turn on {vac}', None), ('en', 'Switch {vac} on', None),
        ('en', 'Can {vac} clean now?', None), ('en', 'I need {vac} to clean the living room', None),
        ('en', 'Do a cleaning pass', None), ('en', 'Make {vac} clean the house', None), ('en', 'Go clean, {vac}', None),
        ('en', 'Start a vacuum run', None), ('en', 'Have {vac} clean up', None), ('en', 'The kitchen needs vacuuming', None),
        ('fr', 'Allume {vac}', None), ('fr', 'Mets {vac} au travail', None), ('fr', 'Envoie {vac} nettoyer', None),
        ('fr', 'Fais le ménage', None), ('fr', 'Nettoie le sol', None), ('fr', 'Démarre un nettoyage', None),
        ('fr', '{vac}, au boulot', None), ('fr', 'Il faut que {vac} nettoie', None), ('fr', 'Lance un cycle de nettoyage', None),
        ('fr', "C'est parti pour le ménage", None), ('fr', 'Fais passer {vac}', None), ('fr', 'Lance {vac} dans la cuisine', None),
        ('fr', 'Mets en marche le nettoyage', None), ('fr', 'Envoie {vac} faire un tour', None)],
    'vacuum.pause': [
        ('en', 'Pause the cleaning', None), ('en', 'Stop cleaning for now', None), ('en', 'Wait, {vac}, pause', None),
        ('en', 'Interrupt {vac}', None), ('en', 'Take a break, {vac}', None), ('en', 'Keep {vac} still for a minute', None),
        ('en', 'Stop {vac} right there', None), ('en', 'Hold {vac} in place', None), ('en', 'Can you halt the cleaning?', None),
        ('en', '{vac} pause', None), ('en', 'Pause the vacuum run, I need quiet', None),
        ('fr', 'Pause le ménage', None), ('fr', "Arrête le nettoyage pour l'instant", None), ('fr', 'Attends {vac}, pause', None),
        ('fr', 'Interromps {vac}', None), ('fr', 'Fais une pause {vac}', None), ('fr', 'Stoppe {vac} là', None),
        ('fr', 'Laisse {vac} en pause', None), ('fr', 'Suspends le nettoyage', None), ('fr', 'Mets le nettoyage sur pause', None),
        ('fr', 'Bloque {vac} sur place', None), ('fr', 'Arrête {vac} où il est', None), ('fr', '{vac} pause', None)],
    'vacuum.dock': [
        ('en', 'Send {vac} to its charger', None), ('en', '{vac}, back to base', None), ('en', 'Recall {vac}', None),
        ('en', 'Bring {vac} home', None), ('en', '{vac} needs to charge', None), ('en', 'Stop and go back to the dock', None),
        ('en', 'Have {vac} return to base', None), ('en', 'Make {vac} go home', None), ('en', 'End cleaning and dock', None),
        ('en', 'Put {vac} away', None), ('en', '{vac} return to the charging station', None),
        ('fr', 'Ramène {vac} à sa station', None), ('fr', '{vac} à la base', None), ('fr', 'Rappelle {vac}', None),
        ('fr', 'Fais revenir {vac} à la base', None), ('fr', 'Termine le ménage et retourne à la base', None),
        ('fr', 'Range {vac} sur sa station', None), ('fr', 'Remets {vac} en charge', None), ('fr', 'Retour base {vac}', None),
        ('fr', '{vac} rentre au dock', None), ('fr', 'Fin du ménage, {vac} à la station de charge', None)],
    'vacuum.seek': [
        ('en', 'Can you find {vac}?', None), ('en', 'Make {vac} play a sound', None), ('en', "I can't see {vac} anywhere", None),
        ('en', 'Where has {vac} gone?', None), ('en', 'Get {vac} to beep', None), ('en', 'Sound the locator on {vac}', None),
        ('en', '{vac} is lost', None), ('en', 'Make some noise {vac} so I can find you', None),
        ('fr', 'Tu sais où est {vac} ?', None), ('fr', 'Fais du bruit avec {vac} pour que je le trouve', None),
        ('fr', 'Je ne vois plus {vac}', None), ('fr', 'Aide-moi à localiser {vac}', None), ('fr', 'Retrouve {vac}', None),
        ('fr', 'Fais un bip sur {vac}', None), ('fr', '{vac} a disparu', None), ('fr', 'Localisation de {vac}', None)],
    'vacuum.empty_dust': [
        ('en', 'Empty the bin of {vac}', None), ('en', 'The dust bin of {vac} is full', None),
        ('en', 'Clean out the bin of {vac}', None), ('en', 'Run the self-empty', None), ('en', 'Empty the dust container', None),
        ('en', 'Get rid of the dust in {vac}', None),
        ('fr', 'Vide {vac}', None), ('fr', 'Le bac de {vac} est plein', None), ('fr', 'Vide le collecteur de {vac}', None),
        ('fr', "Lance l'autovidage", None), ('fr', 'Vide le réservoir à poussière', None),
        ('fr', 'Débarrasse la poussière de {vac}', None)],
    'tv_volume_set': [
        ('en', 'Set the volume to {n} on {tv}', None), ('en', '{tv} volume {n}', None), ('en', 'Volume level {n} for {tv}', None),
        ('en', 'Turn {tv} to {n}', None), ('en', 'Put {tv} on volume {nw}', None), ('en', 'I want {tv} at {n}', None),
        ('en', 'Adjust {tv} volume to {n}', None), ('en', 'Make it {n} on {tv}', None), ('en', '{tv} sound at {nw}', None),
        ('fr', 'Volume de {tv} à {n}', None), ('fr', '{tv} à {n}', None), ('fr', 'Mets {tv} sur {nw}', None),
        ('fr', 'Je veux le son de {tv} à {n}', None), ('fr', 'Règle {tv} sur {n}', None),
        ('fr', 'Ajuste le volume de {tv} à {n}', None), ('fr', 'Son de {tv} sur {nw}', None),
        ('fr', 'Le volume à {n} sur {tv} stp', None)],
    'tv_volume_step_up': [
        ('en', 'Turn up {tv}', None), ('en', 'Louder {tv}', None), ('en', 'Increase {tv} volume', None),
        ('en', 'Bump up {tv}', None), ('en', 'Make {tv} louder', None), ('en', 'Pump up the volume on {tv}', None),
        ('en', 'I can barely hear {tv}', None), ('en', '{tv} volume up one step', None), ('en', 'Up the sound on {tv}', None),
        ('fr', 'Monte {tv}', None), ('fr', 'Augmente le son de {tv}', None), ('fr', 'Mets plus fort {tv}', None),
        ('fr', 'On entend rien sur {tv}', None), ('fr', '{tv} plus fort', None), ('fr', 'Monte un peu le son de {tv}', None),
        ('fr', 'Hausse le volume de {tv}', None), ('fr', 'Un cran plus fort sur {tv}', None), ('fr', 'Pousse le son de {tv}', None)],
    'tv_volume_step_down': [
        ('en', 'Turn down {tv}', None), ('en', 'Quieter {tv}', None), ('en', 'Decrease {tv} volume', None),
        ('en', 'Make {tv} quieter', None), ('en', '{tv} is too loud', None), ('en', 'Lower {tv} a notch', None),
        ('en', 'Reduce the sound on {tv}', None), ('en', 'Tone down {tv}', None),
        ('fr', 'Baisse {tv}', None), ('fr', 'Diminue le son de {tv}', None), ('fr', 'Baisse le volume sur {tv}', None),
        ('fr', 'Mets moins fort {tv}', None), ('fr', '{tv} est trop fort', None), ('fr', '{tv} moins fort', None),
        ('fr', 'Baisse un peu le son de {tv}', None), ('fr', 'Réduis le volume de {tv}', None),
        ('fr', 'Un cran moins fort sur {tv}', None)],
    'app_launch': [
        ('en', 'Open {app}', None), ('en', '{app} on {tv}', None), ('en', 'Switch {tv} to {app}', None),
        ('en', 'Go to {app}', None), ('en', 'Show {app} on {tv}', None), ('en', 'Load {app}', None),
        ('en', 'Turn on {app}', None), ('en', 'Let me watch {app}', None), ('en', 'Bring up {app}', None),
        ('fr', 'Ouvre {app}', None), ('fr', '{app} sur {tv}', None), ('fr', 'Passe {tv} sur {app}', None),
        ('fr', 'Va sur {app}', None), ('fr', 'Affiche {app} sur {tv}', None), ('fr', 'Mets-moi {app}', None),
        ('fr', 'Démarre {app}', None), ('fr', 'Je veux voir {app}', None), ('fr', 'On regarde {app}', None)],
    'ble_scan_room': [
        ('en', 'Scan bluetooth', None), ('en', 'Search for bluetooth devices', None), ('en', 'Which BLE devices are near?', None),
        ('en', 'Bluetooth scan for {s} seconds', 'seconds'), ('en', 'Detect nearby bluetooth', None),
        ('en', 'List bluetooth devices in the room', None), ('en', 'Is there any bluetooth device around?', None),
        ('fr', 'Recherche les appareils bluetooth', None), ('fr', 'Détecte le bluetooth autour', None),
        ('fr', 'Quels appareils BLE sont proches ?', None), ('fr', 'Scan BLE de {s} secondes', 'seconds'),
        ('fr', 'Liste les appareils bluetooth de la pièce', None), ('fr', 'Y a-t-il du bluetooth ici ?', None)],
    'device_facts': [
        ('en', 'Info on {dev}', None), ('en', 'Details for {dev}', None), ('en', 'Show {dev} details', None),
        ('en', 'Specs of {dev}', None), ('en', 'Describe {dev}', None), ('en', 'Everything you know about {dev}', None),
        ('fr', 'Parle-moi de {dev}', None), ('fr', 'Fiche de {dev}', None), ('fr', 'Caractéristiques de {dev}', None),
        ('fr', 'Décris {dev}', None), ('fr', 'Tout ce que tu sais sur {dev}', None), ('fr', 'Infos techniques de {dev}', None)],
    'fabric.status': [
        ('en', 'How many devices are connected?', None), ('en', 'Device count', None), ('en', 'Summarize my devices', None),
        ('en', 'Status of all my devices', None), ('en', 'Which devices are online?', None), ('en', 'Show the fabric status', None),
        ('fr', "Combien d'appareils connectés ?", None), ('fr', "Nombre d'appareils", None), ('fr', 'Résume mes appareils', None),
        ('fr', 'Statut de tous mes appareils', None), ('fr', 'Quels appareils sont en ligne ?', None),
        ('fr', 'Où en sont mes appareils ?', None)],
    'clarify_volume': [
        ('en', 'Make it louder', None), ('en', 'Crank it up', None), ('en', 'Quieter', None), ('en', 'Turn it down', None),
        ('en', 'Set the volume', None), ('en', 'Lower the sound', None),
        ('fr', 'Plus de son', None), ('fr', 'Monte un peu', None), ('fr', 'Moins fort', None), ('fr', 'Baisse le son', None),
        ('fr', 'Mets plus fort', None), ('fr', 'Règle le volume', None)],
    'clarify_vacuum': [
        ('en', 'Start the vacuum then stop it', None), ('en', 'Vacuum on, vacuum off', None), ('en', 'Make the robot do stuff', None),
        ('fr', "Lance puis arrête l'aspirateur", None), ('fr', 'Aspirateur marche arrêt', None), ('fr', 'Occupe-toi du robot', None)],
    'clarify_app': [
        ('en', 'Open something on the TV', None), ('en', 'Start an app', None), ('en', 'Put a show on', None),
        ('fr', 'Affiche quelque chose sur la télé', None), ('fr', 'Lance une application', None), ('fr', 'Mets une série', None)],
    'unsupported': [
        ('en', 'Open the gate', None), ('en', 'Arm the alarm', None), ('en', 'Who is at the door?', None),
        ('en', 'Send a text to Paul', None), ('en', 'What time is it?', None), ('en', 'Find a pancake recipe', None),
        ('en', 'Turn on the lights', None), ('en', 'Start the washing machine', None), ('en', 'Record the front camera', None),
        ('en', 'Delete my emails', None),
        ('fr', 'Ouvre le portail du jardin', None), ('fr', "Arme l'alarme", None), ('fr', 'Qui sonne à la porte ?', None),
        ('fr', 'Envoie un SMS à Paul', None), ('fr', 'Quelle heure est-il ?', None), ('fr', 'Trouve une recette de crêpes', None),
        ('fr', 'Allume la lumière', None), ('fr', 'Lance la machine à laver', None), ('fr', 'Enregistre la caméra', None),
        ('fr', 'Supprime mes mails', None)],
}

# Hand-written test requests no template produces (messy, voice-like, mixed).
NATURAL_TEST = [
    ('fr', 'euh lance l aspi steuplé', 'vacuum.start', {}), ('fr', 'le robot il doit rentrer à sa base', 'vacuum.dock', {}),
    ('en', 'yo can u start the vacuum thx', 'vacuum.start', {}), ('en', 'robot back to the dock now', 'vacuum.dock', {}),
    ('fr', 'mets le son de la télé a 25', 'tv_volume_set', {'value': 25}), ('en', 'tv volume 40 pls', 'tv_volume_set', {'value': 40}),
    ('fr', 'ouvre youtube sur la tele', 'app_launch', {'package': APPS['YouTube']}),
    ('en', 'put netflix on the tv', 'app_launch', {'package': APPS['Netflix']}),
    ('fr', 'c est trop fort baisse la télé', 'tv_volume_step', {'direction': 'down'}),
    ('en', 'too quiet, tv up a notch', 'tv_volume_step', {'direction': 'up'}),
    ('fr', 'y a combien d appareils connectés', 'fabric.status', {}), ('en', 'how many of my devices are up', 'fabric.status', {}),
    ('fr', 'scan bluetooth autour de moi', 'ble_scan_room', {}), ('en', 'any bluetooth stuff near me', 'ble_scan_room', {}),
    ('fr', 'ou est passé le robot aspirateur', 'vacuum.seek', {}), ('en', 'cant find the robot make it beep', 'vacuum.seek', {}),
    ('fr', 'arrête l aspirateur deux minutes', 'vacuum.pause', {}), ('en', 'pause the robot real quick', 'vacuum.pause', {}),
    ('fr', 'vide le bac du robot', 'vacuum.empty_dust', {}), ('en', 'empty the robots bin', 'vacuum.empty_dust', {}),
    ('fr', 'commande moi des sushis', None, 'unsupported'), ('en', 'whats the score of the game', None, 'unsupported'),
    ('fr', 'ouvre la porte du garage', None, 'unsupported'), ('en', 'send my location to Tom', None, 'unsupported'),
    ('fr', 'monte', None, 'clarify'), ('en', 'open an app', None, 'clarify'),
]

TYPO = str.maketrans({'é': 'e', 'è': 'e', 'ê': 'e', 'à': 'a', 'ç': 'c', 'ù': 'u', 'ô': 'o', 'î': 'i'})
FILLERS = {'en': ['', '', 'please ', 'hey OpenBridge, ', 'ok ', 'could you ', 'um ', 'yo '],
           'fr': ['', '', 'stp ', 'OpenBridge, ', 'ok ', 'dis, ', 'euh ', 'vas-y ', 'tu peux ']}
SUFFIXES = {'en': ['', '', '', ' please', ' thx', ' now', ' thanks'], 'fr': ['', '', '', ' stp', ' merci', ' steuplé', ' svp']}


def vary(text, lang, rng):
    t = text
    if rng.random() < 0.35:
        t = rng.choice(FILLERS[lang]) + t[0].lower() + t[1:]
    r = rng.random()
    if r < 0.25:
        t = t.lower().rstrip(' ?!.')                    # voice transcription style
    elif r < 0.35:
        t = t.translate(TYPO).lower()                    # no accents
    if rng.random() < 0.25:
        t = t.rstrip(' ?!.') + rng.choice(SUFFIXES[lang])
    if rng.random() < 0.12 and len(t) > 8:              # one typo: swap or drop a letter
        i = rng.randrange(1, len(t) - 2)
        t = t[:i] + t[i + 1] + t[i] + t[i + 2:] if rng.random() < 0.6 else t[:i] + t[i + 1:]
    return t


def gold(family, slots):
    v, d = 'vacuum', DEV
    simple = {'vacuum.start': ('start cleaning', 'vacuum.start'), 'vacuum.pause': ('pause cleaning', 'vacuum.pause'),
              'vacuum.dock': ('send vacuum to dock', 'vacuum.dock'), 'vacuum.seek': ('make the vacuum beep', 'vacuum.seek'),
              'vacuum.empty_dust': ('empty the dustbin', 'vacuum.empty_dust')}
    if family in simple:
        return reply(simple[family][0], simple[family][1], d(v))
    if family == 'tv_volume_set':
        return reply('set tv volume to %d' % slots['n'], 'tv_volume_set', d('tv'), {'value': slots['n']})
    if family == 'tv_volume_step_up':
        return reply('tv volume up one step', 'tv_volume_step', d('tv'), {'direction': 'up'})
    if family == 'tv_volume_step_down':
        return reply('tv volume down one step', 'tv_volume_step', d('tv'), {'direction': 'down'})
    if family == 'app_launch':
        return reply('open %s on tv' % slots['app'].lower(), 'app_launch', d('tv'), {'package': APPS[slots['app']]})
    if family == 'ble_scan_room':
        return reply('scan nearby bluetooth', 'ble_scan_room', d('relay'), {'seconds': slots['s']} if 's' in slots else {})
    if family == 'device_facts':
        return reply('read facts of %s' % slots['ref'], 'device_facts', d(slots['ref']))
    if family == 'fabric.status':
        return reply('count online devices', 'fabric.status', [{'kind': 'category', 'ref': 'fabric'}])
    if family == 'clarify_volume':
        q = {'en': 'Set an exact volume, or step up once?', 'fr': 'Régler un volume précis, ou monter d\'un cran ?'}[slots['lang']]
        return clarify('ambiguous tv volume set vs step', q, 'set vs step')
    if family == 'clarify_vacuum':
        q = {'en': 'Should the vacuum start, or pause?', 'fr': "L'aspirateur doit-il démarrer, ou se mettre en pause ?"}[slots['lang']]
        return clarify('conflicting vacuum request', q, 'start vs pause')
    if family == 'clarify_app':
        q = {'en': 'Which app should I open on the TV?', 'fr': 'Quelle appli dois-je ouvrir sur la télé ?'}[slots['lang']]
        return clarify('app not named', q, 'which app')
    return unsupported('no registered skill does this')


def expand(family, lang, template, extra, rng, k, noise=True):
    out = []
    for _ in range(k):
        slots = {'lang': lang}
        txt = template
        if '{tv}' in txt:
            txt = txt.replace('{tv}', rng.choice(TV[lang]))
        if '{vac}' in txt:
            txt = txt.replace('{vac}', rng.choice(VAC[lang]))
        if '{n}' in txt:
            slots['n'] = rng.choice([rng.randrange(0, 101), rng.choice([5, 10, 15, 20, 25, 30, 40, 50])])
            txt = txt.replace('{n}', str(slots['n']))
        if '{nw}' in txt:
            slots['n'] = rng.choice(sorted(NUM_WORDS[lang]))
            txt = txt.replace('{nw}', NUM_WORDS[lang][slots['n']])
        if '{app}' in txt:
            slots['app'] = rng.choice(sorted(APPS))
            txt = txt.replace('{app}', rng.choice(APP_ALIASES[slots['app']]))
        if '{dev}' in txt:
            name, slots['ref'] = rng.choice(DEVICES[lang])
            txt = txt.replace('{dev}', name)
        if '{s}' in txt:
            slots['s'] = rng.randrange(3, 16)
            txt = txt.replace('{s}', str(slots['s']))
        if family == 'device_facts' and 'ref' not in slots:
            continue
        if family == 'app_launch' and 'app' not in slots:   # "Launch {app}" always has one
            continue
        out.append({'family': family, 'lang': lang, 'text': vary(txt, lang, rng) if noise else txt,
                    'reply': gold(family, slots)})
    return out


def example(row):
    return {'family': row['family'], 'lang': row['lang'], 'text': row['text'],
            'prompt': build_prompt(row['text'], row['lang']), 'reply': row['reply']}


_ACCENTS = str.maketrans('éèêëàâäçùûüôöîï', 'eeeeaaacuuuooii')


def _words(text):
    t = text.lower().translate(_ACCENTS)
    return set(''.join(ch if ch.isalnum() else ' ' for ch in t).split()) - {'stp', 'please', 'ok', 'merci', 'svp'}


def _leaks(family, lang, template, extra, novel_words, rng):
    """True when this template can produce a near-duplicate (word Jaccard >= 0.7) of an independent test line."""
    for row in expand(family, lang, template, extra, rng, 40, noise=False):
        w = _words(row['text'])
        for nw in novel_words:
            if w and len(w & nw) / len(w | nw) >= 0.7:
                return True
    return False


def novel_rows():
    rows = []
    for lang, text, exp in NOVEL:
        if exp[0] == 'clarify':
            r, fam = clarify('ambiguous request', 'Can you be more specific?', 'underspecified'), 'clarify'
        elif exp[0] == 'unsupported':
            r, fam = unsupported('no registered skill does this'), 'unsupported'
        else:
            _, sid, params, ref = exp
            tg = [{'kind': 'category', 'ref': 'fabric'}] if ref == 'fabric' else DEV(ref)
            r, fam = reply('novel request', sid, tg, params), sid
        rows.append({'family': 'novel/' + fam, 'lang': lang, 'text': text, 'reply': r})
    return rows


def build(seed=7, per_template=10, test_per_template=4):
    """Original templates (FAMILIES) always train/test as in v1. An independent line that one of them can echo is a
    canonical phrasing, so it leaves novel.jsonl (reported as novel_canonical_removed). A v2 EXTRA template that can
    echo an independent line is dropped from the data (reported as templates_dropped_for_leakage)."""
    rng = random.Random(seed)
    novel = novel_rows()
    canonical = set()
    for family, ts in FAMILIES.items():
        for lang, tpl, extra in ts:
            for row in expand(family, lang, tpl, extra, random.Random(1), 40, noise=False):
                w = _words(row['text'])
                for i, r in enumerate(novel):
                    nw = _words(r['text'])
                    if w and len(w & nw) / len(w | nw) >= 0.7:
                        canonical.add(i)
    removed = [novel[i]['text'] for i in sorted(canonical)]
    novel = [r for i, r in enumerate(novel) if i not in canonical]
    novel_words = [_words(r['text']) for r in novel]
    train, test, dropped = [], [], []
    for family in FAMILIES:
        by_lang = {}
        for t in FAMILIES[family]:
            by_lang.setdefault(t[0], []).append(t)
        for t in EXTRA.get(family, []):
            if _leaks(family, *t, novel_words, random.Random(1)):
                dropped.append(t[1])
            else:
                by_lang.setdefault(t[0], []).append(t)
        for lang, ts in by_lang.items():
            rng.shuffle(ts)
            n_test = max(1, len(ts) // 5)                 # 20 % of templates are test-only
            k_train = per_template if family != 'unsupported' else 3
            k_test = test_per_template if family != 'unsupported' else 2
            for lang_, tpl, extra in ts[n_test:]:
                train += expand(family, lang_, tpl, extra, rng, k_train)
            for lang_, tpl, extra in ts[:n_test]:
                test += expand(family, lang_, tpl, extra, rng, k_test)
    for lang, text, sid, params in NATURAL_TEST:
        if sid is None and params == 'unsupported':
            r = unsupported('no registered skill does this')
        elif sid is None:
            r = clarify('ambiguous request', 'Can you be more specific?', 'underspecified')
        else:
            tg = [{'kind': 'category', 'ref': 'fabric'}] if sid == 'fabric.status' else \
                 DEV('relay' if sid == 'ble_scan_room' else 'tv' if sid.startswith(('tv_', 'app_')) else 'vacuum')
            r = reply('natural request', sid, tg, params)
        test.append({'family': 'natural', 'lang': lang, 'text': text, 'reply': r})
    held_out = {r['text'].lower() for r in test} | {r['text'].lower() for r in novel}
    train = [r for r in train if r['text'].lower() not in held_out]   # no exact duplicates across splits
    seen, uniq = set(), []
    for r in train:                                                    # no repeated identical training lines
        if r['text'].lower() not in seen:
            seen.add(r['text'].lower())
            uniq.append(r)
    rng.shuffle(uniq)
    return [example(r) for r in uniq], [example(r) for r in test], [example(r) for r in novel], dropped, removed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default='E:/OpenBridgeAI/data_v2')
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    train, test, novel, dropped, removed = build(a.seed)
    for name, rows in (('train', train), ('test', test), ('novel', novel)):
        with open(out / ('%s.jsonl' % name), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps({'train': len(train), 'test': len(test), 'novel': len(novel),
                      'templates_dropped_for_leakage': dropped, 'novel_canonical_removed': removed,
                      'out': str(out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
