package fr.openbridge.companion;

import android.app.Activity;
import android.app.TimePickerDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Settings made on the phone itself: modules, context profiles, which messages reach the glasses, standalone mode,
 *  and diagnostics. Module changes are the same switches the PC sees (get_status) and can flip (set_modules). */
public class SettingsActivity extends Activity {
    private RelayServer relay;
    private LinearLayout profilesBox, appsBox;
    private Button autoBtn;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        relay = RelayServer.get(this, null);
        LinearLayout col = Look.page(this, L.t("Settings"), L.t("Modules, profiles, messages on the glasses, standalone mode."));

        // ---- modules ----
        LinearLayout mc = Look.card(this);
        mc.addView(Look.section(this, L.t("Modules")));
        for (String m : RelayServer.MODULES) {
            Button t = Look.add(mc, Look.toggle(this, moduleLabel(m), relay.module(m)), 6);
            t.setOnClickListener(v -> {
                boolean on = !(Boolean) v.getTag();
                if ("sensors".equals(m)) { startActivity(new Intent(this, SensorsActivity.class)); return; }
                relay.setModule(m, on);
                Look.setToggle(t, moduleLabel(m), on);
            });
        }
        Look.add(mc, Look.text(this, L.t("The PC sees the same switches (Controls > Modules) and the glasses hide the menus that are off."), 12, false, Look.FAINT), 8);
        Look.add(col, mc, 0);

        // ---- profiles ----
        LinearLayout pc = Look.card(this);
        pc.addView(Look.section(this, L.t("Profiles")));
        autoBtn = Look.toggle(this, L.t("Switch automatically"), Profiles.auto(this));
        autoBtn.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); Profiles.setAuto(this, on); Look.setToggle(autoBtn, L.t("Switch automatically"), on); renderProfiles(); });
        pc.addView(autoBtn);
        profilesBox = new LinearLayout(this); profilesBox.setOrientation(LinearLayout.VERTICAL);
        Look.add(pc, profilesBox, 6);
        Look.add(col, pc, 14);
        renderProfiles();

        // ---- messages ----
        SharedPreferences f = NotifListener.filter(this);
        LinearLayout nc = Look.card(this);
        nc.addView(Look.section(this, L.t("Messages on the glasses")));
        Button access = Look.button(this, NotifListener.accessGranted(this) ? L.t("Notification access: allowed") : L.t("Allow notification access"), Look.CYAN, false);
        access.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        nc.addView(access);
        Button priv = Look.add(nc, Look.toggle(this, L.t("Hide the text (sender only)"), f.getBoolean("private", false)), 6);
        priv.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); f.edit().putBoolean("private", on).apply(); Look.setToggle(priv, L.t("Hide the text (sender only)"), on); });
        Button quiet = Look.add(nc, Look.toggle(this, quietLabel(f), f.getBoolean("quiet", false)), 6);
        quiet.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); f.edit().putBoolean("quiet", on).apply(); Look.setToggle(quiet, quietLabel(f), on); });
        Button hours = Look.add(nc, Look.button(this, L.t("Change the quiet hours"), Look.MUTED, false), 6);
        hours.setOnClickListener(v -> pickQuiet(f, quiet));
        Look.add(nc, Look.text(this, L.t("Apps whose messages reach the glasses:"), 13, false, Look.MUTED), 12);
        appsBox = new LinearLayout(this); appsBox.setOrientation(LinearLayout.VERTICAL);
        Look.add(nc, appsBox, 4);
        Button more = Look.add(nc, Look.button(this, L.t("Show all apps"), Look.MUTED, false), 8);
        more.setOnClickListener(v -> { renderApps(true); more.setEnabled(false); });
        renderApps(false);
        Look.add(col, nc, 14);

        // ---- standalone ----
        LinearLayout sc = Look.card(this);
        sc.addView(Look.section(this, L.t("Standalone mode")));
        Button sa = Look.toggle(this, L.t("Drive the glasses from the phone when the PC is away"), StandaloneHub.enabled(this));
        sa.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); StandaloneHub.setEnabled(this, on); Look.setToggle(sa, L.t("Drive the glasses from the phone when the PC is away"), on); });
        sc.addView(sa);
        Look.add(sc, Look.text(this, L.t("After 20 s without the PC, the phone shows the clock, messages, sport and Oracle answers on the glasses. The PC takes over again by itself, and gets the sport sessions."), 12, false, Look.FAINT), 6);
        Look.add(col, sc, 14);

        // ---- more ----
        LinearLayout dc = Look.card(this);
        dc.addView(Look.section(this, L.t("More")));
        Button diag = Look.button(this, L.t("Diagnostics and log"), Look.CYAN, false);
        diag.setOnClickListener(v -> startActivity(new Intent(this, DiagnosticsActivity.class)));
        dc.addView(diag);
        Button ai = Look.add(dc, Look.button(this, L.t("AI on this phone"), Look.VIOLET, false), 8);
        ai.setOnClickListener(v -> startActivity(new Intent(this, AiActivity.class)));
        Look.add(col, dc, 14);
    }

    static String moduleLabel(String m) {
        switch (m) {
            case "oracle": return L.t("Oracle");
            case "messages": return L.t("Messages");
            case "sport": return L.t("Sport");
            case "tv": return L.t("TV");
            case "vacuum": return L.t("Vacuum");
            case "sensors": return L.t("Phone sensors");
            default: return m;
        }
    }

    private void renderProfiles() {
        profilesBox.removeAllViews();
        JSONArray l = Profiles.list(this);
        String cur = Profiles.current(this);
        for (int i = 0; i < l.length(); i++) {
            JSONObject p = l.optJSONObject(i);
            if (p == null) continue;
            String id = p.optString("id");
            boolean on = id.equals(cur);
            Button bt = Look.add(profilesBox, Look.button(this, (on ? "● " : "○ ") + Profiles.label(id, p.optString("name")) + "   ·   " + ruleText(p.optJSONObject("rule")), on ? Look.OK : Look.MUTED, false), 6);
            bt.setOnClickListener(v -> {
                if (Profiles.auto(this)) { Profiles.setAuto(this, false); Look.setToggle(autoBtn, L.t("Switch automatically"), false); }
                Profiles.apply(this, id, false);
                renderProfiles();
            });
            bt.setOnLongClickListener(v -> { editRule(l, p); return true; });
        }
        Look.add(profilesBox, Look.text(this, L.t("Tap to use a profile now; hold to change its rule."), 12, false, Look.FAINT), 6);
    }

    private String ruleText(JSONObject r) {
        if (r == null) return L.t("by hand");
        switch (r.optString("type")) {
            case "sensor": return L.t("when a sport sensor connects");
            case "wifi": return r.optString("ssid").isEmpty() ? L.t("on a Wi-Fi network (to set)") : L.t("on Wi-Fi") + " " + r.optString("ssid");
            case "time": return r.optString("from") + "-" + r.optString("to");
            default: return L.t("by hand");
        }
    }

    private void editRule(JSONArray l, JSONObject p) {
        JSONObject r = p.optJSONObject("rule");
        if (r == null) return;
        try {
            switch (r.optString("type")) {
                case "wifi": {
                    String now = Profiles.ssid(this);
                    if (now.isEmpty()) {
                        requestPermissions(new String[]{"android.permission.ACCESS_FINE_LOCATION"}, 41);
                        android.widget.Toast.makeText(this, L.t("Connect to the network first (Android needs location access to read its name)."), android.widget.Toast.LENGTH_LONG).show();
                        return;
                    }
                    r.put("ssid", now);
                    break;
                }
                case "time": {
                    int from = Profiles.minutes(r.optString("from"));
                    new TimePickerDialog(this, (tp, h, m) -> {
                        try { r.put("from", String.format(Locale.ROOT, "%02d:%02d", h, m)); } catch (Exception ignored) { }
                        int to = Profiles.minutes(r.optString("to"));
                        new TimePickerDialog(this, (tp2, h2, m2) -> {
                            try { r.put("to", String.format(Locale.ROOT, "%02d:%02d", h2, m2)); Profiles.save(this, l); } catch (Exception ignored) { }
                            renderProfiles();
                        }, to / 60, to % 60, true).show();
                    }, from / 60, from % 60, true).show();
                    return;
                }
                default: return;
            }
            Profiles.save(this, l);
            renderProfiles();
        } catch (Exception ignored) { }
    }

    private String quietLabel(SharedPreferences f) {
        int a = f.getInt("quiet_from", 22 * 60), b = f.getInt("quiet_to", 7 * 60);
        return String.format(Locale.ROOT, "%s %02d:%02d-%02d:%02d", L.t("Quiet hours"), a / 60, a % 60, b / 60, b % 60);
    }

    private void pickQuiet(SharedPreferences f, Button quiet) {
        int a = f.getInt("quiet_from", 22 * 60);
        new TimePickerDialog(this, (tp, h, m) -> {
            f.edit().putInt("quiet_from", h * 60 + m).apply();
            int b = f.getInt("quiet_to", 7 * 60);
            new TimePickerDialog(this, (tp2, h2, m2) -> {
                f.edit().putInt("quiet_to", h2 * 60 + m2).apply();
                Look.setToggle(quiet, quietLabel(f), f.getBoolean("quiet", false));
            }, b / 60, b % 60, true).show();
        }, a / 60, a % 60, true).show();
    }

    private void renderApps(boolean all) {
        appsBox.removeAllViews();
        SharedPreferences f = NotifListener.filter(this);
        Set<String> chosen = new HashSet<>(NotifListener.chosen(this));
        PackageManager pm = getPackageManager();
        List<String[]> apps = new ArrayList<>();      // {label, package}
        Set<String> seen = new HashSet<>();
        Intent main = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        for (ResolveInfo ri : pm.queryIntentActivities(main, 0)) {
            String pkg = ri.activityInfo.packageName;
            if (!seen.add(pkg) || pkg.equals(getPackageName())) continue;
            boolean known = NotifListener.APPS.contains(pkg) || chosen.contains(pkg);
            if (!all && !known) continue;
            if (all && !known && (ri.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0 && !pkg.contains("messag")) continue;
            apps.add(new String[]{String.valueOf(ri.loadLabel(pm)), pkg});
        }
        Collections.sort(apps, (x, y) -> x[0].compareToIgnoreCase(y[0]));
        if (apps.isEmpty()) appsBox.addView(Look.text(this, L.t("No messaging app found."), 13, false, Look.MUTED));
        for (String[] a : apps) {
            Button t = Look.add(appsBox, Look.toggle(this, a[0], chosen.contains(a[1])), 4);
            t.setOnClickListener(v -> {
                boolean on = !(Boolean) v.getTag();
                Set<String> s = new HashSet<>(NotifListener.chosen(this));
                if (on) s.add(a[1]); else s.remove(a[1]);
                f.edit().putStringSet("apps", s).apply();
                Look.setToggle(t, a[0], on);
            });
        }
    }
}
