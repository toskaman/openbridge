package fr.openbridge.companion;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

/** Diagnostics: the relay and glasses link, how fast each PC request was answered, and the recent log. Export
 *  shares it as plain text (the owner chooses where it goes); nothing is sent by itself. */
public class DiagnosticsActivity extends Activity {
    private final Handler h = new Handler(Looper.getMainLooper());
    private TextView link, ops, log;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        LinearLayout col = Look.page(this, L.t("Diagnostics"), L.t("Kept in memory only. Export it when you report a problem."));
        link = block(col, L.t("Link"));
        ops = block(col, L.t("PC requests (answer time)"));
        log = block(col, L.t("Recent log"));
        Button exp = Look.add(col, Look.button(this, L.t("Export"), Look.CYAN, true), 14);
        exp.setOnClickListener(v -> {
            Intent i = new Intent(Intent.ACTION_SEND).setType("text/plain")
                    .putExtra(Intent.EXTRA_SUBJECT, "OpenBridge Companion diagnostics")
                    .putExtra(Intent.EXTRA_TEXT, report());
            startActivity(Intent.createChooser(i, L.t("Export")));
        });
        h.post(tick);
    }

    private TextView block(LinearLayout col, String title) {
        LinearLayout c = Look.card(this);
        c.addView(Look.section(this, title));
        TextView t = Look.text(this, "", 12, false, Look.TEXT);
        t.setTypeface(Typeface.MONOSPACE);
        t.setTextIsSelectable(true);
        c.addView(t);
        Look.add(col, c, col.getChildCount() > 2 ? 14 : 0);
        return t;
    }

    private String linkText() {
        RelayServer r = RelayServer.get(this, null);
        StringBuilder s = new StringBuilder();
        s.append("Companion 0.15.0 · Android ").append(Build.VERSION.RELEASE).append(" · ").append(Build.MODEL).append('\n');
        s.append(L.t("Paired")).append(": ").append(r.paired()).append('\n');
        try {
            JSONObject g = r.glasses().status();
            s.append(L.t("Glasses")).append(": ").append(g.optString("state")).append(' ').append(g.optString("name"))
                    .append("  MTU ").append(g.optInt("mtu")).append('\n')
                    .append("  ").append(L.t("chunks")).append(' ').append(g.optLong("written")).append(", ").append(L.t("errors")).append(' ').append(g.optLong("write_errors"))
                    .append(", ").append(L.t("gestures")).append(' ').append(g.optLong("gestures")).append('\n');
            if (!g.optString("error").isEmpty()) s.append("  ").append(g.optString("error")).append('\n');
        } catch (Exception ignored) { }
        s.append(L.t("Mirror frames")).append(": ").append(GlassesLink.MIRROR.frames).append('\n');
        s.append(L.t("Profile")).append(": ").append(Profiles.current(this).isEmpty() ? "-" : Profiles.current(this))
                .append(Profiles.auto(this) ? " (auto)" : "").append('\n');
        s.append(L.t("Standalone")).append(": ").append(StandaloneHub.enabled(this) ? (StandaloneHub.get(this).active() ? L.t("driving the glasses") : L.t("ready")) : L.t("Off")).append('\n');
        s.append(L.t("Phone sensors")).append(": ").append(SensorService.running() ? L.t("On") : L.t("Off"));
        return s.toString();
    }

    private String report() { return linkText() + "\n\n" + Diag.opsText() + "\n" + Diag.logText(); }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            link.setText(linkText());
            ops.setText(Diag.opsText());
            log.setText(Diag.logText());
            h.postDelayed(this, 1500);
        }
    };

    @Override protected void onDestroy() { h.removeCallbacks(tick); super.onDestroy(); }
}
