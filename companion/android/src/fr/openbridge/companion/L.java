package fr.openbridge.companion;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Français / English for the Companion screen. Settings > Language / Langue: Auto (system language, English when
 * it is neither), Français or English. The choice is saved and reported to the paired PC, so the glasses follow it
 * unless the owner set a separate glasses language there. Internal codes and log lines from the relay stay English.
 */
final class L {
    static final String PREF = "language";      // auto | fr | en
    static String lang = "en";
    private static final Map<String, String> FR = new HashMap<>();

    static {
        // ---- 0.15: Glasses, Devices, Sensors, Settings, Diagnostics, AI pages ----
        FR.put("connected", "connectées");
        FR.put("At home", "Maison");
        FR.put("Turn the phone sensors on in the Sensors page.", "Activez les capteurs du téléphone depuis la page Capteurs.");
        FR.put("Phone mode", "Mode telephone");
        FR.put("Session started", "Séance démarrée");
        FR.put("Session stopped", "Séance arrêtée");
        FR.put("Command model", "Modèle de commandes");
        FR.put("Last command", "Dernière commande");
        FR.put("not connected", "non connectées");
        FR.put("AI on this phone", "IA sur ce téléphone");
        FR.put("A small model and speech-to-text running on the phone, without the PC or the internet.", "Un petit modèle et la dictée qui tournent sur le téléphone, sans le PC ni internet.");
        FR.put("Engine and models", "Moteur et modèles");
        FR.put("Models are copied from the PC: openbridge companion ai push (USB debugging on).", "Les modèles sont copiés depuis le PC : openbridge companion ai push (débogage USB activé).");
        FR.put("When the phone answers", "Quand le téléphone répond");
        FR.put("Summarise long messages for the glasses", "Résumer les longs messages pour les lunettes");
        FR.put("Wake word \"OK Bridge\"", "Mot d'éveil \"OK Bridge\"");
        FR.put("The wake word needs the speech model on the phone.", "Le mot d'éveil a besoin du modèle de dictée sur le téléphone.");
        FR.put("The wake word keeps the microphone on with a visible notification and uses more battery. Off by default.", "Le mot d'éveil garde le micro allumé avec une notification visible et consomme plus de batterie. Désactivé par défaut.");
        FR.put("Try it", "Essayer");
        FR.put("Ask the phone…", "Demandez au téléphone…");
        FR.put("Ask the phone", "Demander au téléphone");
        FR.put("Open the Oracle (voice)", "Ouvrir l'Oracle (voix)");
        FR.put("Always on the phone", "Toujours sur le téléphone");
        FR.put("Always on the PC", "Toujours sur le PC");
        FR.put("Auto: on the phone when the PC is away", "Auto : sur le téléphone quand le PC est absent");
        FR.put("Engine", "Moteur");
        FR.put("not in this build", "absent de cette version");
        FR.put("Language model", "Modèle de langage");
        FR.put("Speech model", "Modèle de dictée");
        FR.put("Threads", "Cœurs utilisés");
        FR.put("Last answer", "Dernière réponse");
        FR.put("Last dictation", "Dernière dictée");
        FR.put("No model on the phone yet.", "Pas encore de modèle sur le téléphone.");
        FR.put("Thinking…", "Je réfléchis…");
        FR.put("No answer.", "Pas de réponse.");
        FR.put("Devices", "Appareils");
        FR.put("What each device is doing, sent by your PC.", "Ce que fait chaque appareil, envoyé par votre PC.");
        FR.put("Glasses", "Lunettes");
        FR.put("Phone sensors", "Capteurs du téléphone");
        FR.put("on", "activés");
        FR.put("off", "désactivés");
        FR.put("The PC sends the other devices while OpenBridge runs on it (glasses hub).", "Le PC envoie les autres appareils quand OpenBridge tourne dessus (hub des lunettes).");
        FR.put("Updated", "Mis à jour il y a");
        FR.put("Diagnostics", "Diagnostic");
        FR.put("Kept in memory only. Export it when you report a problem.", "Gardé en mémoire uniquement. Exportez-le pour signaler un problème.");
        FR.put("Link", "Liaison");
        FR.put("PC requests (answer time)", "Requêtes du PC (temps de réponse)");
        FR.put("Recent log", "Journal récent");
        FR.put("Export", "Exporter");
        FR.put("chunks", "paquets");
        FR.put("errors", "erreurs");
        FR.put("gestures", "gestes");
        FR.put("Mirror frames", "Images de l'aperçu");
        FR.put("Profile", "Profil");
        FR.put("Standalone", "Mode autonome");
        FR.put("driving the glasses", "pilote les lunettes");
        FR.put("ready", "prêt");
        FR.put("What your glasses show, and how to drive them from the phone.", "Ce qu'affichent vos lunettes, et comment les piloter depuis le téléphone.");
        FR.put("On the glasses now", "Sur les lunettes en ce moment");
        FR.put("Navigate", "Naviguer");
        FR.put("Next", "Suivant");
        FR.put("Open", "Ouvrir");
        FR.put("Back", "Retour");
        FR.put("Home", "Accueil");
        FR.put("Volume keys: up = next, down = back", "Touches volume : + suivant, − retour");
        FR.put("Controls in the notification and lock screen", "Commandes dans la notification et l'écran verrouillé");
        FR.put("With the notification controls on, the volume keys drive the glasses even with the screen off.", "Avec les commandes en notification, les touches de volume pilotent les lunettes même écran éteint.");
        FR.put("Brightness", "Luminosité");
        FR.put("Reconnect the glasses", "Reconnecter les lunettes");
        FR.put("Close the ENGO app first: the glasses accept one connection at a time.", "Fermez d'abord l'app ENGO : les lunettes n'acceptent qu'une connexion à la fois.");
        FR.put("Turn the crown: next / back", "Tournez la couronne : suivant / retour");
        FR.put("The glasses are not connected.", "Les lunettes ne sont pas connectées.");
        FR.put("Connecting…", "Connexion…");
        FR.put("Connected.", "Connectées.");
        FR.put("Not connected.", "Non connectées.");
        FR.put("Updated live from the frames sent to the glasses", "Mis à jour en direct depuis les images envoyées aux lunettes");
        FR.put("Battery", "Batterie");
        FR.put("Battery unknown", "Batterie inconnue");
        FR.put("Nothing shown yet: the picture appears as soon as something is sent to the glasses.", "Rien d'affiché pour l'instant : l'image apparaît dès que quelque chose est envoyé aux lunettes.");
        FR.put("Glasses remote", "Télécommande des lunettes");
        FR.put("Volume up = next, volume down = back", "Volume + = suivant, volume − = retour");
        FR.put("Glasses: next", "Lunettes : suivant");
        FR.put("Oracle", "Oracle");
        FR.put("Settings", "Réglages");
        FR.put("Sensors", "Capteurs");
        FR.put("The Oracle is turned off for this device.", "L'Oracle est désactivé sur cet appareil.");
        FR.put("Not paired — pair PC first", "Non appairé — appairez d'abord le PC");
        FR.put("phone", "téléphone");
        FR.put("Bike", "Vélo");
        FR.put("Work", "Bureau");
        FR.put("Phone sensors on", "Capteurs du téléphone actifs");
        FR.put("GPS, compass and sport sensors for your glasses", "GPS, boussole et capteurs sport pour vos lunettes");
        FR.put("The phone's GPS, compass and your sport sensors, for the glasses' sport and navigation screens.", "Le GPS, la boussole du téléphone et vos capteurs sport, pour les écrans sport et navigation des lunettes.");
        FR.put("Share with the PC for the glasses", "Partager avec le PC pour les lunettes");
        FR.put("Off by default. When on, your position and sensor values go only to your paired PC, encrypted, and a notification stays visible.", "Désactivé par défaut. Activé, votre position et vos capteurs vont uniquement à votre PC appairé, chiffrés, et une notification reste visible.");
        FR.put("Sport sensors", "Capteurs sport");
        FR.put("Search for sensors (10 s)", "Chercher des capteurs (10 s)");
        FR.put("Heart rate belts, foot pods, speed / cadence sensors, power meters and smart trainers (standard Bluetooth profiles).", "Ceintures cardio, capteurs de foulée, vitesse / cadence, capteurs de puissance et home-trainers (profils Bluetooth standard).");
        FR.put("Visual Oracle", "Oracle visuel");
        FR.put("Take a photo, ask a question: the answer appears on your glasses.", "Prenez une photo, posez une question : la réponse s'affiche dans vos lunettes.");
        FR.put("Photo → Oracle", "Photo → Oracle");
        FR.put("No sensor added yet.", "Aucun capteur ajouté.");
        FR.put("Searching…", "Recherche…");
        FR.put("Tap a sensor to add it", "Touchez un capteur pour l'ajouter");
        FR.put("No sensor found. Wake it up (wear the belt, spin the wheel) and search again.", "Aucun capteur trouvé. Réveillez-le (mettez la ceinture, faites tourner la roue) et relancez.");
        FR.put("heart rate", "cardio");
        FR.put("running speed", "vitesse de course");
        FR.put("speed / cadence", "vitesse / cadence");
        FR.put("power", "puissance");
        FR.put("smart trainer", "home-trainer");
        FR.put("waiting for a fix…", "recherche du signal…");
        FR.put("Compass", "Boussole");
        FR.put("Possible fall", "Chute possible");
        FR.put("Modules, profiles, messages on the glasses, standalone mode.", "Modules, profils, messages sur les lunettes, mode autonome.");
        FR.put("Modules", "Modules");
        FR.put("The PC sees the same switches (Controls > Modules) and the glasses hide the menus that are off.", "Le PC voit les mêmes interrupteurs (Contrôles > Modules) et les lunettes masquent les menus désactivés.");
        FR.put("Profiles", "Profils");
        FR.put("Switch automatically", "Changer automatiquement");
        FR.put("Messages on the glasses", "Messages sur les lunettes");
        FR.put("Notification access: allowed", "Accès aux notifications : autorisé");
        FR.put("Allow notification access", "Autoriser l'accès aux notifications");
        FR.put("Hide the text (sender only)", "Masquer le texte (expéditeur seul)");
        FR.put("Change the quiet hours", "Changer les heures calmes");
        FR.put("Apps whose messages reach the glasses:", "Apps dont les messages arrivent dans les lunettes :");
        FR.put("Show all apps", "Afficher toutes les apps");
        FR.put("Standalone mode", "Mode autonome");
        FR.put("Drive the glasses from the phone when the PC is away", "Piloter les lunettes depuis le téléphone quand le PC est absent");
        FR.put("After 20 s without the PC, the phone shows the clock, messages, sport and Oracle answers on the glasses. The PC takes over again by itself, and gets the sport sessions.", "Après 20 s sans le PC, le téléphone affiche l'heure, les messages, le sport et les réponses de l'Oracle dans les lunettes. Le PC reprend la main tout seul et récupère les séances de sport.");
        FR.put("More", "Plus");
        FR.put("Diagnostics and log", "Diagnostic et journal");
        FR.put("Messages", "Messages");
        FR.put("Sport", "Sport");
        FR.put("TV", "TV");
        FR.put("Vacuum", "Aspirateur");
        FR.put("Tap to use a profile now; hold to change its rule.", "Touchez pour utiliser un profil ; appui long pour changer sa règle.");
        FR.put("by hand", "à la main");
        FR.put("when a sport sensor connects", "quand un capteur sport se connecte");
        FR.put("on a Wi-Fi network (to set)", "sur un réseau Wi-Fi (à choisir)");
        FR.put("on Wi-Fi", "sur le Wi-Fi");
        FR.put("Connect to the network first (Android needs location access to read its name).", "Connectez-vous d'abord au réseau (Android demande l'accès à la position pour lire son nom).");
        FR.put("Quiet hours", "Heures calmes");
        FR.put("No messaging app found.", "Aucune app de messagerie trouvée.");
        FR.put("No PC: phone mode", "Sans PC : mode telephone");
        FR.put("messages", "messages");
        FR.put("No messages", "Aucun message");
        FR.put("New message", "Nouveau message");
        FR.put("SPEED", "VITESSE");
        FR.put("DIST", "DIST");
        FR.put("TIME", "TEMPS");
        FR.put("Open = start", "Ouvrir = depart");
        FR.put("Ask on the phone", "Demandez sur le telephone");
        FR.put("Photo + question → the answer on your glasses.", "Photo + question → la réponse dans vos lunettes.");
        FR.put("Take a photo", "Prendre une photo");
        FR.put("What is this?", "Qu'est-ce que c'est ?");
        FR.put("Ask the Oracle", "Demander à l'Oracle");
        FR.put("No camera app on this phone.", "Aucune app appareil photo sur ce téléphone.");
        FR.put("The photo could not be read.", "La photo n'a pas pu être lue.");
        FR.put("Wake word", "Mot d'éveil");
        FR.put("Listening for \"OK Bridge\"", "À l'écoute de \"OK Bridge\"");
        FR.put("On the phone only. Tap to turn off.", "Sur le téléphone uniquement. Touchez pour désactiver.");
        FR.put("Sent — the answer will show on your glasses", "Envoyé — la réponse s'affichera dans vos lunettes");
        FR.put("Photo too large", "Photo trop grande");
        FR.put("Could not queue the photo", "Impossible d'envoyer la photo");
        FR.put("Paired", "Appairé");
        FR.put("ACTIVITY", "ACTIVITÉ");
        FR.put("Allow", "Autoriser");
        FR.put("Allow Bluetooth scanning", "Autoriser le scan Bluetooth");
        FR.put("Allow full control?", "Autoriser le contrôle total ?");
        FR.put("Allowed", "Autorisé");
        FR.put("Allowed — the PC may act without asking", "Autorisé — le PC peut agir sans demander");
        FR.put("Android blocked the request dialog. Allow the permission on the page that just opened.", "Android a bloqué la demande. Autorisez la permission sur la page qui vient de s'ouvrir.");
        FR.put("Ask OpenBridge…", "Demandez à OpenBridge…");
        FR.put("Ask OpenBridge…  e.g. Start my vacuum", "Demandez à OpenBridge…  ex. Lance l'aspirateur");
        FR.put("Auto", "Auto");
        FR.put("Available", "Disponible");
        FR.put("BLUETOOTH", "BLUETOOTH");
        FR.put("Background relay", "Relais en arrière-plan");
        FR.put("Background relay started", "Relais en arrière-plan démarré");
        FR.put("Background relay stopped", "Relais en arrière-plan arrêté");
        FR.put("Bluetooth LE hardware", "Matériel Bluetooth LE");
        FR.put("Bluetooth scans", "Scans Bluetooth");
        FR.put("CONTROLS", "COMMANDES");
        FR.put("Cancel", "Annuler");
        FR.put("Cancelled", "Annulé");
        FR.put("Companion", "Companion");
        FR.put("Companion started", "Companion démarré");
        FR.put("Confirm", "Confirmer");
        FR.put("Disabled in Settings", "Désactivée dans les paramètres");
        FR.put("ENTER THIS CODE IN OPENBRIDGE ON YOUR PC", "SAISISSEZ CE CODE DANS OPENBRIDGE SUR VOTRE PC");
        FR.put("EXCHANGING", "ÉCHANGE");
        FR.put("Enter the code shown below on your PC.", "Saisissez sur votre PC le code affiché ci-dessous.");
        FR.put("Flow view off", "Vue des flux désactivée");
        FR.put("Flow view on", "Vue des flux activée");
        FR.put("Full control", "Contrôle total");
        FR.put("Full control allowed on this device", "Contrôle total autorisé sur cet appareil");
        FR.put("Full control revoked on this device", "Contrôle total retiré sur cet appareil");
        FR.put("Got it — working on it…", "Compris — je m'en occupe…");
        FR.put("Granted", "Accordée");
        FR.put("Hi. Ask me anything — type, or tap the orb to talk.", "Bonjour. Demandez-moi ce que vous voulez — écrivez, ou touchez l'orbe pour parler.");
        FR.put("Hide", "Masquer");
        FR.put("Hold the button to send", "Maintenez le bouton pour envoyer");
        FR.put("Hold, then confirm", "Maintenez, puis confirmez");
        FR.put("I didn't catch that.", "Je n'ai pas compris.");
        FR.put("I'm listening…", "Je vous écoute…");
        FR.put("LINK", "LIAISON");
        FR.put("LISTENING", "J'ÉCOUTE");
        FR.put("LIVE", "EN DIRECT");
        FR.put("Language", "Langue");
        FR.put("Location services", "Localisation");
        FR.put("Messages on my glasses", "Messages sur mes lunettes");
        FR.put("Microphone declined — type instead.", "Micro refusé — écrivez plutôt.");
        FR.put("Microphone unavailable.", "Micro indisponible.");
        FR.put("NOT PAIRED", "NON APPAIRÉ");
        FR.put("No BLE", "Pas de BLE");
        FR.put("No Bluetooth adapter on this device.", "Pas d'adaptateur Bluetooth sur cet appareil.");
        FR.put("No answer from the PC — timed out.", "Pas de réponse du PC — délai dépassé.");
        FR.put("None", "Aucune");
        FR.put("Not granted yet", "Pas encore accordée");
        FR.put("Not paired", "Non appairé");
        FR.put("Not present", "Absent");
        FR.put("Not yet", "Pas encore");
        FR.put("OFFLINE", "HORS LIGNE");
        FR.put("Off", "Désactivé");
        FR.put("Off (Android 11 and older)", "Désactivée (Android 11 et avant)");
        FR.put("Offline", "Hors ligne");
        FR.put("On", "Activé");
        FR.put("Open OpenBridge on your PC to pair this device.", "Ouvrez OpenBridge sur votre PC pour appairer cet appareil.");
        FR.put("PAIRED", "APPAIRÉ");
        FR.put("PAIRING", "APPAIRAGE");
        FR.put("Pair with your PC first.", "Appairez d'abord votre PC.");
        FR.put("Paired", "Appairé");
        FR.put("Paired with a PC", "Appairé à un PC");
        FR.put("Paired. Ask me anything — type, or tap the orb to talk.", "Appairé. Demandez-moi ce que vous voulez — écrivez, ou touchez l'orbe pour parler.");
        FR.put("Pairing removed. Open OpenBridge on your PC to pair again.", "Appairage supprimé. Ouvrez OpenBridge sur votre PC pour appairer à nouveau.");
        FR.put("Pairing requested by a PC", "Appairage demandé par un PC");
        FR.put("Pairing…", "Appairage…");
        FR.put("Paused", "En pause");
        FR.put("Paused by you", "Mis en pause par vous");
        FR.put("QUICK CONTROLS", "COMMANDES RAPIDES");
        FR.put("READY", "PRÊT");
        FR.put("RECEIVING", "RÉCEPTION");
        FR.put("Remove pairing", "Supprimer l'appairage");
        FR.put("SCANNING NEARBY", "SCAN À PROXIMITÉ");
        FR.put("SCANS", "SCANS");
        FR.put("SENDING", "ENVOI");
        FR.put("SPEAKING", "JE PARLE");
        FR.put("SYSTEM & PERMISSIONS", "SYSTÈME ET AUTORISATIONS");
        FR.put("Scan permission", "Permission de scan");
        FR.put("Scanning", "Scan en cours");
        FR.put("Scans", "Scans");
        FR.put("Scans paused by you", "Scans mis en pause par vous");
        FR.put("Scans resumed", "Scans repris");
        FR.put("Sending…", "Envoi…");
        FR.put("Set up everything", "Tout configurer");
        FR.put("Show", "Afficher");
        FR.put("Starting…", "Démarrage…");
        FR.put("System Bluetooth app", "Appli Bluetooth système");
        FR.put("THINKING", "RÉFLEXION");
        FR.put("Tap the orb or Stop to send (15 s max).", "Touchez l'orbe ou Stop pour envoyer (15 s max).");
        FR.put("Too short — hold a little longer.", "Trop court — maintenez un peu plus.");
        FR.put("Turn Bluetooth on from the quick settings panel, then come back.", "Activez le Bluetooth depuis les réglages rapides, puis revenez.");
        FR.put("Turn Bluetooth on in Settings > Remotes & Accessories, then come back.", "Activez le Bluetooth dans Paramètres > Télécommandes et accessoires, puis revenez.");
        FR.put("Turn on Bluetooth", "Activer le Bluetooth");
        FR.put("Turning Bluetooth on…", "Activation du Bluetooth…");
        FR.put("View flows", "Voir les flux");
        FR.put("Voice cancelled.", "Voix annulée.");
        FR.put("Voice recording is not supported on this device.", "L'enregistrement vocal n'est pas pris en charge sur cet appareil.");
        FR.put("WAITING FOR YOUR PC", "EN ATTENTE DE VOTRE PC");
        FR.put("While this app is open", "Tant que l'appli est ouverte");
        FR.put("Yes", "Oui");
        FR.put("hold to send", "maintenir pour envoyer");
        FR.put("Oracle ENGO", "Oracle ENGO");
        FR.put("Live mic -> ENGO 3", "Micro direct -> ENGO 3");
        FR.put("Listening… speak naturally", "J'écoute… parlez naturellement");
        FR.put("Stop Oracle", "Arrêter Oracle");
        FR.put("Last question", "Dernière question");
        FR.put("ENGO 3 answer", "Réponse ENGO 3");
        FR.put("ENGO 3 Controls", "Contrôles ENGO 3");
        FR.put("Requested ENGO 3 controls…", "Contrôles ENGO 3 demandés…");
    }

    private L() {}

    static String setting(Context c) {
        return prefs(c).getString(PREF, "auto");
    }

    static void init(Context c) {
        String s = setting(c);
        lang = "fr".equals(s) || "en".equals(s) ? s : ("fr".equals(Locale.getDefault().getLanguage()) ? "fr" : "en");
    }

    /** The language in use (fr or en), resolving Auto against the system language. */
    static String resolved(Context c) {
        init(c);
        return lang;
    }

    /** auto -> fr -> en -> auto. Returns the new setting. */
    static String cycle(Context c) {
        String s = setting(c);
        String next = "auto".equals(s) ? "fr" : "fr".equals(s) ? "en" : "auto";
        prefs(c).edit().putString(PREF, next).apply();
        init(c);
        return next;
    }

    static String label(Context c) {
        String s = setting(c);
        return "Language / Langue : " + ("fr".equals(s) ? "Français" : "en".equals(s) ? "English" : t("Auto"));
    }

    static String t(String en) {
        if (!"fr".equals(lang)) return en;
        String f = FR.get(en);
        return f != null ? f : en;
    }

    private static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences("openbridge-ui", Context.MODE_PRIVATE);
    }
}
