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
