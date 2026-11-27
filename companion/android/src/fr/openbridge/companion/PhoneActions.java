package fr.openbridge.companion;

import android.content.Context;

import org.json.JSONObject;

/** Orders the phone carries out itself, as understood by its own command model (LocalAi.intent): glasses
 *  navigation, modules, profiles, the standalone sport session, glasses brightness, standalone mode. They only change
 *  this phone's settings and what the glasses show; anything that acts on another device stays with the PC. */
final class PhoneActions {
    private PhoneActions() { }

    /** Runs one understood order. Returns a short confirmation, or null when it is a question ({"a":"ask"}) or not
     *  something the phone does. */
    static String run(Context c, JSONObject o) { return run(c, o, null); }

    /** Words that must appear for the orders a model could confuse with an order for another device ("turn the tv
     *  down" must never stop standalone mode). Defence in depth on top of the model's training. */
    static boolean mentions(String said, String kind) {
        if (said == null) return true;
        String p = WakeService.plain(said);
        switch (kind) {
            case "standalone": return p.matches(".*(autonom|standalone|sans pc|no pc|toi meme|yourself|rends la main|give .*back).*");
            case "sport": return p.matches(".*(seance|chrono|entrain|sortie|session|workout|run|ride|timer|depart|velo|course|go go|fini|done|finish).*");
            case "luma": return p.matches(".*(lumin|bright|dim|sombre|dark|clair).*");
            // glasses menus are named with "module" / "menu" ("eteins la tele" is for the TV itself, the PC's job)
            case "module": return p.matches(".*(module|menu|oracle|assistant|capteur|sensor|gps|lunettes|glasses|ecrans|screens).*");
            default: return true;
        }
    }

    static String run(Context c, JSONObject o, String said) {
        if (o == null) return null;
        if (!mentions(said, o.optString("a"))) { Diag.log("phone order ignored (wording): " + o); return null; }
        RelayServer r = RelayServer.get(c, null);
        switch (o.optString("a")) {
            case "nav": {
                String v = o.optString("v");
                if (!v.matches("next|ok|back|home")) return null;
                r.glasses().button(v);
                return L.t("Glasses") + ": " + L.t(v.equals("ok") ? "Open" : v.equals("next") ? "Next" : v.equals("back") ? "Back" : "Home");
            }
            case "module": {
                String m = o.optString("m");
                if (!RelayServer.knownModule(m) || !o.has("on")) return null;
                boolean on = o.optBoolean("on");
                if ("sensors".equals(m) && on) return L.t("Turn the phone sensors on in the Sensors page.");
                r.setModule(m, on);
                return SettingsActivity.moduleLabel(m) + ": " + L.t(on ? "On" : "Off");
            }
            case "profile": {
                String p = o.optString("p");
                if (Profiles.find(c, p) == null) return null;
                Profiles.apply(c, p, false);
                return L.t("Profile") + ": " + Profiles.label(p, p);
            }
            case "sport": {
                String v = o.optString("v");
                if (!v.matches("start|stop")) return null;
                StandaloneHub.get(c).session("start".equals(v));
                return L.t("start".equals(v) ? "Session started" : "Session stopped");
            }
            case "luma": {
                android.content.SharedPreferences gp = c.getSharedPreferences(GlassesActivity.PREFS, Context.MODE_PRIVATE);
                int now = gp.getInt("luma", 12), v;
                Object val = o.opt("v");
                if ("up".equals(val)) v = Math.min(15, now + 3);
                else if ("down".equals(val)) v = Math.max(0, now - 3);
                else if (val instanceof Number) v = Math.max(0, Math.min(15, ((Number) val).intValue()));
                else return null;
                gp.edit().putInt("luma", v).apply();
                final int lv = v;
                GlassesLink g = r.glasses();
                if ("READY".equals(g.state())) new Thread(() -> { try { g.writeLocal(AL.luma(lv)); } catch (Exception ignored) { } }).start();
                return L.t("Brightness") + " " + v;
            }
            case "standalone": {
                if (!o.has("on")) return null;
                boolean on = o.optBoolean("on");
                StandaloneHub.setEnabled(c, on);
                return L.t("Standalone mode") + ": " + L.t(on ? "On" : "Off");
            }
            default:
                return null;
        }
    }
}
