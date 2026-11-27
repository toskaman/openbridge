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

/** Devices page: one card per device, with what it is doing now. The PC sends the cards (op set_cards: TV volume
 *  and app, vacuum state and battery, unread messages...); the glasses and the phone's sensors are added here.
 *  Display only: actions stay in Quick controls and the glasses, behind the PC's checks. */
public class DevicesActivity extends Activity {
    private final Handler h = new Handler(Looper.getMainLooper());
    private LinearLayout box;
    private TextView age;
    private String shown = "";

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        LinearLayout col = Look.page(this, L.t("Devices"), L.t("What each device is doing, sent by your PC."));
        box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        col.addView(box);
        age = Look.add(col, Look.text(this, "", 12, false, Look.FAINT), 10);
        h.post(tick);
    }

    private static int tone(String t) {
        switch (t) {
            case "ok": return Look.OK;
            case "warn": return Look.WARN;
            case "alert": return Look.ERR;
            case "muted": return Look.MUTED;
            default: return Look.CYAN;
        }
    }

    private void card(String title, String state, String detail, int colour, Class<?> open) {
        LinearLayout c = Look.card(this);
        TextView t = Look.text(this, title, 17, true, Look.TEXT);
        c.addView(t);
        TextView s = Look.add(c, Look.text(this, "● " + state, 14, false, colour), 4);
        s.setTextColor(colour);
        if (!detail.isEmpty()) Look.add(c, Look.text(this, detail, 13, false, Look.MUTED), 2);
        if (open != null) c.setOnClickListener(v -> startActivity(new Intent(this, open)));
        Look.add(box, c, box.getChildCount() == 0 ? 0 : 10);
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            RelayServer r = RelayServer.get(DevicesActivity.this, null);
            JSONArray cards = r.cards();
            GlassesLink g = r.glasses();
            String key = cards.toString() + g.state() + SensorService.running();
            if (!key.equals(shown)) {
                shown = key;
                box.removeAllViews();
                boolean ready = "READY".equals(g.state());
                card(g.name().isEmpty() ? L.t("Glasses") : g.name(), L.t(ready ? "connected" : "not connected"), "", ready ? Look.OK : Look.MUTED, GlassesActivity.class);
                for (int i = 0; i < cards.length(); i++) {
                    JSONObject c = cards.optJSONObject(i);
                    if (c == null || c.optString("id").equals("glasses")) continue;
                    card(c.optString("title"), c.optString("state"), c.optString("detail"), tone(c.optString("tone")), null);
                }
                card(L.t("Phone sensors"), SensorService.running() ? L.t("on") : L.t("off"), "", SensorService.running() ? Look.OK : Look.MUTED, SensorsActivity.class);
                if (cards.length() == 0) Look.add(box, Look.text(DevicesActivity.this, L.t("The PC sends the other devices while OpenBridge runs on it (glasses hub)."), 13, false, Look.MUTED), 10);
            }
            long at = r.cardsAt();
            age.setText(at == 0 ? "" : L.t("Updated") + " " + Math.max(0, (System.currentTimeMillis() - at) / 1000) + " s");
            h.postDelayed(this, 2000);
        }
    };

    @Override protected void onDestroy() { h.removeCallbacks(tick); super.onDestroy(); }
}
