package fr.openbridge.companion;

import android.content.Context;
import android.content.SharedPreferences;
import android.location.Location;
import android.os.BatteryManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.Calendar;
import java.util.Locale;

/** Standalone mode: phone + glasses + sensors, no PC. When the owner allows it and the PC has not driven the glasses
 *  for a while, the phone draws a small set of screens itself (clock, messages, sport, Oracle answers) and takes the
 *  glasses' taps and the phone's buttons. As soon as the PC drives the glasses again, the phone steps back and tells
 *  it to redraw (event "RESUMED"); sport sessions recorded meanwhile are handed to the PC (op get_sessions).
 *
 *  Nothing here acts on other devices: standalone screens only show information. */
final class StandaloneHub {
    static final long PC_IDLE_MS = 20_000;
    private static StandaloneHub instance;
    static synchronized StandaloneHub get(Context c) { if (instance == null) instance = new StandaloneHub(c.getApplicationContext()); return instance; }

    static boolean enabled(Context c) { return c.getSharedPreferences("standalone", Context.MODE_PRIVATE).getBoolean("enabled", false); }
    static void setEnabled(Context c, boolean on) {
        c.getSharedPreferences("standalone", Context.MODE_PRIVATE).edit().putBoolean("enabled", on).apply();
        if (on) get(c).start(); else get(c).stop();
    }

    private final Context ctx;
    private final SharedPreferences prefs;
    private volatile boolean running, active;
    private volatile long pcSeenAt = System.currentTimeMillis();
    private Thread loop;
    private int screen;                    // 0 clock, 1 messages, 2 sport, 3 oracle
    private static final int SCREENS = 4;
    private int msgIndex;
    private final ArrayDeque<JSONObject> messages = new ArrayDeque<>();
    private volatile String oracleQ = "", oracleA = "";
    private int oraclePage;
    private byte[] last;
    // sport session
    private long sessionStart, sessionPaused;
    private double distanceM;
    private Location lastFix;

    private StandaloneHub(Context c) { ctx = c; prefs = c.getSharedPreferences("standalone", Context.MODE_PRIVATE); }

    /** Called on every glasses_* op from the PC: the PC is driving the glasses. */
    void pcSeen() {
        pcSeenAt = System.currentTimeMillis();
        if (active) release();
    }

    boolean active() { return active; }

    synchronized void start() {
        if (running) return;
        running = true;
        loop = new Thread(this::run, "standalone-hub");
        loop.setDaemon(true);
        loop.start();
        Diag.log("standalone mode allowed");
    }

    synchronized void stop() {
        running = false;
        if (active) release();
        if (loop != null) loop.interrupt();
    }

    private void run() {
        long lastConnect = 0;
        while (running) {
            try {
                GlassesLink g = RelayServer.get(ctx, null).glasses();
                boolean pcIdle = System.currentTimeMillis() - pcSeenAt > PC_IDLE_MS;
                if (pcIdle && !"READY".equals(g.state()) && !g.lastAddress().isEmpty() && System.currentTimeMillis() - lastConnect > 30_000) {
                    lastConnect = System.currentTimeMillis();
                    try { g.connect(g.lastAddress(), "ENGO", 8); g.writeLocal(AL.gestureOn()); } catch (Exception e) { Diag.log("standalone: " + e.getMessage()); }
                }
                if (pcIdle && "READY".equals(g.state()) && !active) take(g);
                if (active) { tickSport(); draw(false); }
                Thread.sleep(1000);
            } catch (InterruptedException e) { return; }
            catch (Exception e) { Diag.log("standalone: " + e); }
        }
    }

    private void take(GlassesLink g) {
        active = true;
        g.setTap(this::onEvent);
        last = null;
        Diag.log("standalone: the phone drives the glasses (no PC for " + PC_IDLE_MS / 1000 + " s)");
        draw(true);
    }

    private void release() {
        active = false;
        GlassesLink g = RelayServer.get(ctx, null).glasses();
        g.setTap(null);
        g.button("home");                               // the PC's hub goes home and redraws everything
        try { g.injectState("RESUMED"); } catch (Exception ignored) { }
        Diag.log("standalone: the PC drives the glasses again");
    }

    /** Glasses / phone events while active: ENGO 3 double tap = next; phone buttons next / ok / back / home. */
    private boolean onEvent(JSONObject e) {
        String t = e.optString("t");
        if ("flow".equals(t) || "tx".equals(t)) return true;
        if ("state".equals(t)) { active = false; return false; }
        String ev = "gesture".equals(t) || "touch".equals(t) ? "next" : "button".equals(t) ? e.optString("v") : null;
        if (ev == null) return true;
        press(ev);
        return true;
    }

    synchronized void press(String ev) {
        switch (ev) {
            case "next":
                if (screen == 1 && messages.size() > 1) { msgIndex = (msgIndex + 1) % messages.size(); break; }
                if (screen == 3 && oraclePages() > 1 && oraclePage + 1 < oraclePages()) { oraclePage++; break; }
                screen = (screen + 1) % SCREENS; msgIndex = 0; oraclePage = 0; break;
            case "ok":
                if (screen == 2) toggleSession();
                break;
            case "back": screen = (screen + SCREENS - 1) % SCREENS; break;
            case "home": screen = 0; break;
            default: return;
        }
        draw(true);
    }

    /** A message from the phone's notifications (NotifListener), shown on top for a few seconds. */
    synchronized void message(JSONObject m) {
        messages.addFirst(m);
        while (messages.size() > 20) messages.removeLast();
        if (active && !"off".equals(Profiles.notifMode(ctx))) { screen = 1; msgIndex = 0; draw(true); }
    }

    /** An Oracle answer computed on the phone (local model): shown on the Oracle screen. */
    synchronized void oracle(String question, String answer) {
        oracleQ = question == null ? "" : question;
        oracleA = answer == null ? "" : answer;
        oraclePage = 0;
        if (active) { screen = 3; draw(true); }
    }

    private int oraclePages() { return Math.max(1, (GlassesPanel.wrap(oracleA, 2, GlassesPanel.X1 - GlassesPanel.X0, 99).size() + 2) / 3); }

    // ---- sport ----------------------------------------------------------------------------------
    /** Start or stop the phone's sport session (voice, or Open on the Sport screen). */
    synchronized void session(boolean start) {
        if (start == (sessionStart != 0)) return;
        toggleSession();
        if (active) { screen = 2; draw(true); }
    }

    private void toggleSession() {
        long now = System.currentTimeMillis();
        if (sessionStart == 0) { sessionStart = now; sessionPaused = 0; distanceM = 0; lastFix = null; Diag.log("standalone: sport session started"); }
        else { saveSession(now); sessionStart = 0; }
    }

    private void tickSport() {
        if (sessionStart == 0) return;
        try {
            JSONObject loc = PhoneSensors.get(ctx).snapshot().optJSONObject("location");
            if (loc == null || loc.optDouble("accuracy_m", 99) > 30 || loc.optDouble("age_s", 99) > 5) return;
            Location l = new Location("gps");
            l.setLatitude(loc.optDouble("lat")); l.setLongitude(loc.optDouble("lon"));
            if (lastFix != null) { float d = lastFix.distanceTo(l); if (d > 2 && d < 200) distanceM += d; }
            lastFix = l;
        } catch (Exception ignored) { }
    }

    private void saveSession(long end) {
        try {
            JSONArray list = new JSONArray(prefs.getString("sessions", "[]"));
            list.put(new JSONObject().put("start", sessionStart / 1000).put("end", end / 1000).put("distance_m", Math.round(distanceM)).put("source", "phone_standalone"));
            while (list.length() > 50) list.remove(0);
            prefs.edit().putString("sessions", list.toString()).apply();
            Diag.log("standalone: sport session saved (" + Math.round(distanceM) + " m)");
        } catch (Exception ignored) { }
    }

    /** Sessions recorded without the PC, handed over once (op get_sessions) and then forgotten here. */
    JSONArray takeSessions() {
        JSONArray a;
        try { a = new JSONArray(prefs.getString("sessions", "[]")); } catch (Exception e) { a = new JSONArray(); }
        prefs.edit().remove("sessions").apply();
        return a;
    }

    // ---- drawing --------------------------------------------------------------------------------
    private synchronized void draw(boolean force) {
        GlassesLink g = RelayServer.get(ctx, null).glasses();
        if (!active || !"READY".equals(g.state())) return;
        GlassesPanel p = new GlassesPanel(true).begin();
        statusBar(p, g);
        switch (screen) {
            case 1: drawMessages(p); break;
            case 2: drawSport(p); break;
            case 3: drawOracle(p); break;
            default: drawClock(p); break;
        }
        p.center(GlassesPanel.CX, 210, dots(), 0, GlassesPanel.MUTED);
        byte[] frame = p.end();
        if (!force && last != null && java.util.Arrays.equals(frame, last)) return;
        last = frame;
        try { g.writeLocal(frame); } catch (Exception e) { Diag.log("standalone draw: " + e.getMessage()); }
    }

    private String dots() { StringBuilder b = new StringBuilder(); for (int i = 0; i < SCREENS; i++) b.append(i == screen ? "o" : ".").append(' '); return b.toString().trim(); }

    private void statusBar(GlassesPanel p, GlassesLink g) {
        Calendar k = Calendar.getInstance();
        p.text(GlassesPanel.X0, 6, String.format(Locale.ROOT, "%02d:%02d", k.get(Calendar.HOUR_OF_DAY), k.get(Calendar.MINUTE)), 1, GlassesPanel.SECONDARY);
        int bat = g.battery();
        BatteryManager bm = (BatteryManager) ctx.getSystemService(Context.BATTERY_SERVICE);
        int phone = bm == null ? -1 : bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        // left: time, then a "phone mode" mark; right: glasses battery, phone battery after "P"
        p.text(GlassesPanel.X0 + 70, 6, "PH", 0, GlassesPanel.ACCENT);
        p.right(GlassesPanel.X1, 6, (bat >= 0 ? bat + "%" : "") + (phone >= 0 ? "  P" + phone + "%" : ""), 0, GlassesPanel.MUTED);
    }

    private void drawClock(GlassesPanel p) {
        Calendar k = Calendar.getInstance();
        p.center(GlassesPanel.CX, 52, String.format(Locale.ROOT, "%02d:%02d", k.get(Calendar.HOUR_OF_DAY), k.get(Calendar.MINUTE)), 5, GlassesPanel.PRIMARY);
        String[] days = L.lang.equals("fr") ? new String[]{"dim", "lun", "mar", "mer", "jeu", "ven", "sam"} : new String[]{"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
        p.center(GlassesPanel.CX, 140, days[k.get(Calendar.DAY_OF_WEEK) - 1] + " " + k.get(Calendar.DAY_OF_MONTH), 2, GlassesPanel.SECONDARY);
        p.center(GlassesPanel.CX, 182, messages.isEmpty() ? L.t("Phone mode") : messages.size() + " " + L.t("messages"), 1, GlassesPanel.MUTED);
    }

    private void drawMessages(GlassesPanel p) {
        if (messages.isEmpty()) { p.center(GlassesPanel.CX, 100, L.t("No messages"), 2, GlassesPanel.MUTED); return; }
        JSONObject m = (JSONObject) messages.toArray()[Math.min(msgIndex, messages.size() - 1)];
        boolean priv = "private".equals(Profiles.notifMode(ctx));
        p.text(GlassesPanel.X0, 34, GlassesPanel.fit(m.optString("sender"), 2, GlassesPanel.X1 - GlassesPanel.X0 - 50), 2, GlassesPanel.PRIMARY);
        p.right(GlassesPanel.X1, 42, (msgIndex + 1) + "/" + messages.size(), 1, GlassesPanel.ACCENT);
        String body = priv ? L.t("New message") : m.optString("text");
        java.util.List<String> lines = GlassesPanel.wrap(body, 1, GlassesPanel.X1 - GlassesPanel.X0, 5);
        for (int i = 0; i < lines.size(); i++) p.text(GlassesPanel.X0, 78 + i * 26, lines.get(i), 1, GlassesPanel.SECONDARY);
    }

    private void drawSport(GlassesPanel p) {
        JSONObject s;
        try { s = PhoneSensors.get(ctx).snapshot(); } catch (Exception e) { s = new JSONObject(); }
        JSONObject loc = s.optJSONObject("location");
        double kmh = loc != null && loc.optDouble("age_s", 99) < 5 ? loc.optDouble("speed_mps", 0) * 3.6 : -1;
        p.text(GlassesPanel.X0, 32, L.t("SPEED"), 0, GlassesPanel.MUTED);
        p.text(GlassesPanel.X0, 52, kmh < 0 ? "--" : String.format(Locale.ROOT, "%.1f", kmh), 5, GlassesPanel.PRIMARY);
        p.text(GlassesPanel.X0 + GlassesPanel.width(kmh < 0 ? "--" : String.format(Locale.ROOT, "%.1f", kmh), 5) + 6, 110, "km/h", 0, GlassesPanel.SECONDARY);
        JSONArray sp = s.optJSONArray("sport");
        for (int i = 0; sp != null && i < sp.length(); i++) {
            JSONObject r = sp.optJSONObject(i);
            if (r != null && r.has("bpm") && r.optDouble("age_s", 99) < 10) { p.right(GlassesPanel.X1, 52, r.optInt("bpm") + "", 2, GlassesPanel.ALERT); p.right(GlassesPanel.X1, 92, "bpm", 0, GlassesPanel.MUTED); }
        }
        p.line(GlassesPanel.X0, 140, GlassesPanel.X1, 140, GlassesPanel.MUTED);
        long el = sessionStart == 0 ? 0 : (System.currentTimeMillis() - sessionStart) / 1000;
        p.text(GlassesPanel.X0, 146, L.t("DIST"), 0, GlassesPanel.MUTED);
        p.text(GlassesPanel.X0, 168, distanceM < 1000 ? Math.round(distanceM) + " m" : String.format(Locale.ROOT, "%.2f km", distanceM / 1000), 2, GlassesPanel.PRIMARY);
        p.text(GlassesPanel.CX + 6, 146, L.t("TIME"), 0, GlassesPanel.MUTED);
        p.text(GlassesPanel.CX + 6, 168, sessionStart == 0 ? L.t("Open = start") : String.format(Locale.ROOT, "%d:%02d", el / 60, el % 60), sessionStart == 0 ? 0 : 2, sessionStart == 0 ? GlassesPanel.ACCENT : GlassesPanel.PRIMARY);
    }

    private void drawOracle(GlassesPanel p) {
        p.text(GlassesPanel.X0, 34, GlassesPanel.fit("> " + (oracleQ.isEmpty() ? L.t("Ask on the phone") : oracleQ), 1, GlassesPanel.X1 - GlassesPanel.X0), 1, GlassesPanel.SECONDARY);
        p.line(GlassesPanel.X0, 62, GlassesPanel.X1, 62, GlassesPanel.MUTED);
        java.util.List<String> lines = GlassesPanel.wrap(oracleA, 2, GlassesPanel.X1 - GlassesPanel.X0, 99);
        for (int i = 0; i < 3 && oraclePage * 3 + i < lines.size(); i++) p.text(GlassesPanel.X0, 68 + i * 40, lines.get(oraclePage * 3 + i), 2, GlassesPanel.OK);
        if (oraclePages() > 1) p.right(GlassesPanel.X1, 186, (oraclePage + 1) + "/" + oraclePages(), 1, GlassesPanel.ACCENT);
    }
}
