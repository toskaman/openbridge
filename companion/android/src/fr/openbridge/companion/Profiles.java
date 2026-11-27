package fr.openbridge.companion;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Calendar;

/** Context profiles: "Bike", "Home", "Work"... Each one sets the modules, the glasses' brightness and how messages
 *  reach the glasses. The owner picks one by hand, or lets the phone switch by itself on a rule: a time window, a
 *  Wi-Fi network, or a sport sensor connecting. The current profile is reported to the PC (get_status). */
final class Profiles {
    static final String PREFS = "profiles";
    private static volatile boolean started;

    private Profiles() { }

    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    private static JSONObject p(String id, String name, int luma, String notif, String rule, Object... mods) throws Exception {
        JSONObject m = new JSONObject();
        for (int i = 0; i < mods.length; i += 2) m.put((String) mods[i], mods[i + 1]);
        return new JSONObject().put("id", id).put("name", name).put("luma", luma).put("notif", notif)
                .put("modules", m).put("rule", new JSONObject(rule));
    }

    static JSONArray list(Context c) {
        try {
            String s = prefs(c).getString("list", null);
            if (s != null) return new JSONArray(s);
            JSONArray d = new JSONArray()
                    .put(p("home", "Home", 10, "all", "{\"type\":\"wifi\",\"ssid\":\"\"}",
                            "oracle", true, "messages", true, "sport", false, "tv", true, "vacuum", true, "sensors", false))
                    .put(p("bike", "Bike", 15, "private", "{\"type\":\"sensor\"}",
                            "oracle", true, "messages", true, "sport", true, "tv", false, "vacuum", false))
                    .put(p("work", "Work", 8, "private", "{\"type\":\"time\",\"from\":\"09:00\",\"to\":\"18:00\",\"days\":\"12345\"}",
                            "oracle", true, "messages", true, "sport", false, "tv", false, "vacuum", false, "sensors", false));
            prefs(c).edit().putString("list", d.toString()).apply();
            return d;
        } catch (Exception e) { return new JSONArray(); }
    }

    static void save(Context c, JSONArray list) { prefs(c).edit().putString("list", list.toString()).apply(); }

    static String current(Context c) { return prefs(c).getString("current", ""); }
    static boolean auto(Context c) { return prefs(c).getBoolean("auto", false); }
    static void setAuto(Context c, boolean on) { prefs(c).edit().putBoolean("auto", on).apply(); if (on) check(c); }

    /** How messages reach the glasses under the current profile: all | private (sender only) | off. */
    static String notifMode(Context c) { return prefs(c).getString("notif", "all"); }

    static JSONObject find(Context c, String id) {
        JSONArray l = list(c);
        for (int i = 0; i < l.length(); i++) { JSONObject o = l.optJSONObject(i); if (o != null && id.equals(o.optString("id"))) return o; }
        return null;
    }

    static String label(String id, String name) {
        switch (id) {
            case "home": return L.t("At home");
            case "bike": return L.t("Bike");
            case "work": return L.t("Work");
            default: return name;
        }
    }

    static void apply(Context c, String id, boolean byRule) {
        JSONObject pr = find(c, id);
        if (pr == null) return;
        RelayServer r = RelayServer.get(c, null);
        JSONObject m = pr.optJSONObject("modules");
        // A profile may switch the phone sensors off, never on: sharing the position is turned on by the owner on
        // the Sensors page only.
        if (m != null) for (String k : RelayServer.MODULES)
            if (m.has(k) && !("sensors".equals(k) && m.optBoolean(k))) r.setModule(k, m.optBoolean(k, true));
        prefs(c).edit().putString("current", id).putString("notif", pr.optString("notif", "all")).apply();
        int luma = pr.optInt("luma", -1);
        if (luma >= 0) {
            c.getSharedPreferences(GlassesActivity.PREFS, Context.MODE_PRIVATE).edit().putInt("luma", luma).apply();
            GlassesLink g = r.glasses();
            if ("READY".equals(g.state())) new Thread(() -> { try { g.writeLocal(AL.luma(luma)); } catch (Exception ignored) { } }).start();
        }
        Diag.log("profile " + id + (byRule ? " (automatic)" : ""));
    }

    static String ssid(Context c) {
        try {
            WifiManager w = (WifiManager) c.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            @SuppressWarnings("deprecation") WifiInfo i = w == null ? null : w.getConnectionInfo();
            String s = i == null ? null : i.getSSID();
            if (s == null || s.contains("unknown ssid")) return "";
            return s.replace("\"", "");
        } catch (Exception e) { return ""; }
    }

    static boolean matches(Context c, JSONObject rule) {
        if (rule == null) return false;
        switch (rule.optString("type")) {
            case "sensor": return PhoneSensors.get(c).sportSensorConnected();
            case "wifi": { String want = rule.optString("ssid"); return !want.isEmpty() && want.equals(ssid(c)); }
            case "time": {
                Calendar k = Calendar.getInstance();
                int dow = ((k.get(Calendar.DAY_OF_WEEK) + 5) % 7) + 1;      // 1 = Monday ... 7 = Sunday
                String days = rule.optString("days", "1234567");
                if (days.indexOf((char) ('0' + dow)) < 0) return false;
                int now = k.get(Calendar.HOUR_OF_DAY) * 60 + k.get(Calendar.MINUTE);
                int from = minutes(rule.optString("from", "00:00")), to = minutes(rule.optString("to", "23:59"));
                return from <= to ? now >= from && now < to : now >= from || now < to;
            }
            default: return false;
        }
    }

    static int minutes(String hhmm) {
        try { String[] a = hhmm.split(":"); return Integer.parseInt(a[0]) * 60 + Integer.parseInt(a[1]); } catch (Exception e) { return 0; }
    }

    /** Sensor rules first (they say the most), then Wi-Fi, then time windows. */
    static void check(Context c) {
        if (!auto(c)) return;
        JSONArray l = list(c);
        for (String type : new String[]{"sensor", "wifi", "time"}) {
            for (int i = 0; i < l.length(); i++) {
                JSONObject pr = l.optJSONObject(i);
                if (pr == null || !type.equals(pr.optJSONObject("rule") == null ? "" : pr.optJSONObject("rule").optString("type"))) continue;
                if (matches(c, pr.optJSONObject("rule"))) {
                    if (!pr.optString("id").equals(current(c))) apply(c, pr.optString("id"), true);
                    return;
                }
            }
        }
    }

    static synchronized void startAuto(Context ctx) {
        if (started) return;
        started = true;
        final Context c = ctx.getApplicationContext();
        Thread t = new Thread(() -> {
            while (true) {
                try { check(c); } catch (Exception ignored) { }
                try { Thread.sleep(60_000); } catch (InterruptedException e) { return; }
            }
        }, "profiles-auto");
        t.setDaemon(true);
        t.start();
    }
}
