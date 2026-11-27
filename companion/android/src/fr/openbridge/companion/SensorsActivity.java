package fr.openbridge.companion;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Locale;
import java.util.Map;

/** Sensors page: the phone's GPS, compass and fall alert, and Bluetooth sport sensors, for the glasses' sport and
 *  navigation screens; plus the visual Oracle (photo -> answer on the glasses). */
public class SensorsActivity extends Activity {
    private final Handler h = new Handler(Looper.getMainLooper());
    private PhoneSensors ps;
    private RelayServer relay;
    private Button run;
    private TextView live, foundTitle;
    private LinearLayout saved, found;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        ps = PhoneSensors.get(this);
        relay = RelayServer.get(this, null);
        LinearLayout col = Look.page(this, L.t("Sensors"), L.t("The phone's GPS, compass and your sport sensors, for the glasses' sport and navigation screens."));

        LinearLayout c1 = Look.card(this);
        c1.addView(Look.section(this, L.t("Phone sensors")));
        run = Look.toggle(this, L.t("Share with the PC for the glasses"), SensorService.running() && relay.module("sensors"));
        c1.addView(run);
        run.setOnClickListener(v -> toggle());
        Look.add(c1, Look.text(this, L.t("Off by default. When on, your position and sensor values go only to your paired PC, encrypted, and a notification stays visible."), 12, false, Look.FAINT), 6);
        live = Look.add(c1, Look.text(this, "", 13, false, Look.TEXT), 12);
        live.setTypeface(android.graphics.Typeface.MONOSPACE);
        Look.add(col, c1, 0);

        LinearLayout c2 = Look.card(this);
        c2.addView(Look.section(this, L.t("Sport sensors")));
        saved = new LinearLayout(this); saved.setOrientation(LinearLayout.VERTICAL);
        c2.addView(saved);
        Button scan = Look.add(c2, Look.button(this, L.t("Search for sensors (10 s)"), Look.CYAN, false), 10);
        scan.setOnClickListener(v -> scan());
        foundTitle = Look.add(c2, Look.text(this, "", 12, false, Look.FAINT), 8);
        found = new LinearLayout(this); found.setOrientation(LinearLayout.VERTICAL);
        c2.addView(found);
        Look.add(c2, Look.text(this, L.t("Heart rate belts, foot pods, speed / cadence sensors, power meters and smart trainers (standard Bluetooth profiles)."), 12, false, Look.FAINT), 8);
        Look.add(col, c2, 14);

        LinearLayout c3 = Look.card(this);
        c3.addView(Look.section(this, L.t("Visual Oracle")));
        c3.addView(Look.text(this, L.t("Take a photo, ask a question: the answer appears on your glasses."), 13, false, Look.MUTED));
        Button vis = Look.add(c3, Look.button(this, L.t("Photo → Oracle"), Look.MAGENTA, true), 10);
        vis.setOnClickListener(v -> startActivity(new Intent(this, VisionActivity.class)));
        Look.add(col, c3, 14);

        renderSaved();
        h.post(tick);
    }

    private void toggle() {
        boolean on = !(Boolean) run.getTag();
        if (on) {
            java.util.List<String> ask = new java.util.ArrayList<>();
            if (!ps.locationPermission()) ask.add("android.permission.ACCESS_FINE_LOCATION");
            if (android.os.Build.VERSION.SDK_INT >= 31 && !ps.blePermission()) { ask.add("android.permission.BLUETOOTH_SCAN"); ask.add("android.permission.BLUETOOTH_CONNECT"); }
            if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
                ask.add("android.permission.POST_NOTIFICATIONS");
            if (!ask.isEmpty()) requestPermissions(ask.toArray(new String[0]), 31);
            relay.setModule("sensors", true);
            SensorService.start(this);
        } else {
            SensorService.stop(this);
            relay.setModule("sensors", false);
        }
        Look.setToggle(run, L.t("Share with the PC for the glasses"), on);
    }

    @Override public void onRequestPermissionsResult(int code, String[] p, int[] r) {
        if (code == 31 && SensorService.running()) { SensorService.stop(this); SensorService.start(this); }   // pick up the new permissions
    }

    private void renderSaved() {
        saved.removeAllViews();
        Map<String, String> m = ps.saved();
        if (m.isEmpty()) { saved.addView(Look.text(this, L.t("No sensor added yet."), 13, false, Look.MUTED)); return; }
        for (Map.Entry<String, String> e : m.entrySet()) {
            String[] kn = e.getValue().split("\\|", 2);
            Button bt = Look.add(saved, Look.button(this, kn[1] + " · " + kindLabel(kn[0]) + "   ✕", Look.MUTED, false), 6);
            bt.setOnClickListener(v -> { ps.forget(e.getKey()); renderSaved(); });
        }
    }

    private void scan() {
        found.removeAllViews();
        if (!ps.blePermission() && android.os.Build.VERSION.SDK_INT >= 31) {
            requestPermissions(new String[]{"android.permission.BLUETOOTH_SCAN", "android.permission.BLUETOOTH_CONNECT"}, 32);
            return;
        }
        foundTitle.setText(L.t("Searching…"));
        ps.scan((addr, name, kind) -> h.post(() -> {
            foundTitle.setText(L.t("Tap a sensor to add it"));
            Button bt = Look.add(found, Look.button(this, "+ " + name + " · " + kindLabel(kind), Look.OK, false), 6);
            bt.setOnClickListener(v -> { ps.save(addr, kind, name); found.removeView(bt); renderSaved(); });
        }));
        h.postDelayed(() -> { if (found.getChildCount() == 0) foundTitle.setText(L.t("No sensor found. Wake it up (wear the belt, spin the wheel) and search again.")); }, 10_500);
    }

    static String kindLabel(String k) {
        switch (k) {
            case "heart_rate": return L.t("heart rate");
            case "rsc": return L.t("running speed");
            case "csc": return L.t("speed / cadence");
            case "power": return L.t("power");
            case "trainer": return L.t("smart trainer");
            default: return k;
        }
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            try {
                JSONObject s = ps.snapshot();
                StringBuilder b = new StringBuilder();
                JSONObject loc = s.optJSONObject("location");
                if (loc != null) b.append(String.format(Locale.ROOT, "GPS   %.5f, %.5f  ±%.0f m%n      %.1f km/h  %s%n",
                        loc.optDouble("lat"), loc.optDouble("lon"), loc.optDouble("accuracy_m"), loc.optDouble("speed_mps", 0) * 3.6,
                        loc.optDouble("age_s") > 5 ? "(" + Math.round(loc.optDouble("age_s")) + " s)" : ""));
                else b.append("GPS   ").append(ps.running() ? L.t("waiting for a fix…") : "—").append('\n');
                b.append(L.t("Compass")).append("  ").append(s.has("heading_deg") ? s.optInt("heading_deg") + "°" : "—").append('\n');
                JSONArray sp = s.optJSONArray("sport");
                for (int i = 0; sp != null && i < sp.length(); i++) {
                    JSONObject r = sp.getJSONObject(i);
                    b.append(kindLabel(r.optString("kind"))).append("  ").append(r.has("bpm") ? r.optInt("bpm") + " bpm" : r.optString("raw"))
                            .append(r.optDouble("age_s") > 5 ? "  (" + Math.round(r.optDouble("age_s")) + " s)" : "").append('\n');
                }
                if (s.has("fall_age_s") && s.optDouble("fall_age_s") < 300) b.append(L.t("Possible fall")).append(" ").append(Math.round(s.optDouble("fall_age_s"))).append(" s\n");
                live.setText(b.toString().trim());
            } catch (Exception ignored) { }
            h.postDelayed(this, 1000);
        }
    };

    @Override protected void onDestroy() { h.removeCallbacks(tick); super.onDestroy(); }
}
