package fr.openbridge.companion;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.drawable.BitmapDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

/** Glasses page: what the glasses show right now (drawn from the frames sent to them), the link and battery, big
 *  Next / Open / Back / Home buttons, the phone's volume keys as a remote, brightness, controls in the notification,
 *  and reconnecting the glasses from the phone. */
public class GlassesActivity extends Activity {
    static final String PREFS = "glasses";
    private final Handler h = new Handler(Looper.getMainLooper());
    private GlassesLink link;
    private SharedPreferences prefs;
    private ImageView screen;
    private TextView state, info, mirrorInfo;
    private Button volumeKeys, notifControls, reconnect;
    private volatile boolean connecting;
    /** On a watch (or a phone without the glasses link) the buttons drive the glasses through the paired PC. */
    private boolean viaPc;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        link = RelayServer.get(this, null).glasses();
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        viaPc = getPackageManager().hasSystemFeature(android.content.pm.PackageManager.FEATURE_WATCH);
        if (viaPc) { buildWatch(); return; }
        LinearLayout col = Look.page(this, L.t("Glasses"), L.t("What your glasses show, and how to drive them from the phone."));

        // ---- live screen ----
        LinearLayout sc = Look.card(this);
        sc.addView(Look.section(this, L.t("On the glasses now")));
        screen = new ImageView(this);
        screen.setAdjustViewBounds(true);
        screen.setScaleType(ImageView.ScaleType.FIT_CENTER);
        screen.setBackground(Look.round(this, Color.BLACK, Look.GLASS_LINE, 14));
        int p = Look.dp(this, 6);
        screen.setPadding(p, p, p, p);
        sc.addView(screen, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Look.dp(this, 230)));
        mirrorInfo = Look.add(sc, Look.text(this, "", 12, false, Look.FAINT), 6);
        Look.add(col, sc, 0);

        // ---- navigation ----
        LinearLayout nav = Look.card(this);
        nav.addView(Look.section(this, L.t("Navigate")));
        Button next = nav("next", L.t("Next"), true), open = nav("ok", L.t("Open"), true),
                back = nav("back", L.t("Back"), false), home = nav("home", L.t("Home"), false);
        nav.addView(Look.row(this, next, open));
        Look.add(nav, Look.row(this, back, home), 8);
        volumeKeys = Look.add(nav, Look.toggle(this, L.t("Volume keys: up = next, down = back"), prefs.getBoolean("volume_keys", true)), 10);
        volumeKeys.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); prefs.edit().putBoolean("volume_keys", on).apply(); Look.setToggle(volumeKeys, L.t("Volume keys: up = next, down = back"), on); });
        notifControls = Look.add(nav, Look.toggle(this, L.t("Controls in the notification and lock screen"), GlassesRemoteService.running(this)), 8);
        notifControls.setOnClickListener(v -> {
            boolean on = !(Boolean) v.getTag();
            if (on) {
                if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
                    requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 21);
                GlassesRemoteService.start(this);
            } else GlassesRemoteService.stop(this);
            prefs.edit().putBoolean("remote_service", on).apply();
            Look.setToggle(notifControls, L.t("Controls in the notification and lock screen"), on);
        });
        Look.add(nav, Look.text(this, L.t("With the notification controls on, the volume keys drive the glasses even with the screen off."), 12, false, Look.FAINT), 6);
        Look.add(col, nav, 14);

        // ---- link ----
        LinearLayout lk = Look.card(this);
        lk.addView(Look.section(this, L.t("Link")));
        state = Look.text(this, "", 18, true, Look.TEXT);
        lk.addView(state);
        info = Look.add(lk, Look.text(this, "", 13, false, Look.MUTED), 4);
        Look.add(lk, Look.text(this, L.t("Brightness"), 13, false, Look.MUTED), 12);
        SeekBar luma = new SeekBar(this);
        luma.setMax(15);
        luma.setProgress(prefs.getInt("luma", 12));
        luma.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int v, boolean user) { if (user) setLuma(v); }
            @Override public void onStartTrackingTouch(SeekBar s) { }
            @Override public void onStopTrackingTouch(SeekBar s) { }
        });
        Look.add(lk, luma, 4);
        reconnect = Look.add(lk, Look.button(this, L.t("Reconnect the glasses"), Look.CYAN, false), 12);
        reconnect.setOnClickListener(v -> reconnect());
        Look.add(lk, Look.text(this, L.t("Close the ENGO app first: the glasses accept one connection at a time."), 12, false, Look.FAINT), 6);
        Look.add(col, lk, 14);

        GlassesLink.MIRROR.setListener(bm -> h.post(() -> show(bm)));
        if (GlassesLink.MIRROR.last() != null) show(GlassesLink.MIRROR.last());
        h.post(tick);
    }

    private Button nav(String ev, String label, boolean primary) {
        Button b = Look.button(this, label, Look.MAGENTA, primary);
        b.setMinHeight(Look.dp(this, 64));
        b.setTextSize(18);
        final String word = "ok".equals(ev) ? "open" : ev;
        b.setOnClickListener(v -> press(viaPc ? word : ev));
        return b;
    }

    /** Watch: four big buttons and the crown (turn = next / back); presses go to the PC, which drives the glasses. */
    private void buildWatch() {
        LinearLayout col = Look.page(this, L.t("Glasses"), L.t("Turn the crown: next / back"));
        Button next = nav("next", L.t("Next"), true), open = nav("ok", L.t("Open"), true),
                back = nav("back", L.t("Back"), false), home = nav("home", L.t("Home"), false);
        col.addView(Look.row(this, back, next));
        Look.add(col, Look.row(this, home, open), 8);
        info = Look.add(col, Look.text(this, "", 12, false, Look.MUTED), 8);
    }

    @Override public boolean onGenericMotionEvent(android.view.MotionEvent e) {
        if (e.getAction() == android.view.MotionEvent.ACTION_SCROLL && e.isFromSource(android.view.InputDevice.SOURCE_ROTARY_ENCODER)) {
            float d = -e.getAxisValue(android.view.MotionEvent.AXIS_SCROLL);
            long now = System.currentTimeMillis();
            if (Math.abs(d) > 0.5f && now - lastCrown > 350) { lastCrown = now; press(d > 0 ? "next" : "back"); }
            return true;
        }
        return super.onGenericMotionEvent(e);
    }
    private long lastCrown;

    private void press(String ev) {
        if (viaPc) {
            RelayServer r = RelayServer.get(this, null);
            if (!r.paired()) { info.setText(L.t("Pair with your PC first.")); return; }
            String s = r.submitCommand(ev);           // "next", "open", "back", "home": the PC's glasses hub presses it
            info.setText(L.t(s));
            return;
        }
        if (!"READY".equals(link.state())) { info.setText(L.t("The glasses are not connected.")); return; }
        link.button(ev);          // to the PC, or to the phone's own hub in standalone mode (GlassesLink tap)
    }

    private void setLuma(int v) {
        prefs.edit().putInt("luma", v).apply();
        new Thread(() -> { try { link.writeLocal(AL.luma(v)); } catch (Exception ignored) { } }, "glasses-luma").start();
    }

    private void reconnect() {
        if (connecting) return;
        connecting = true;
        reconnect.setEnabled(false);
        info.setText(L.t("Connecting…"));
        new Thread(() -> {
            String msg;
            try { link.connect(link.lastAddress(), "ENGO", 8); link.writeLocal(AL.gestureOn()); msg = L.t("Connected."); }
            catch (Exception e) { msg = e.getMessage() == null ? L.t("Not connected.") : e.getMessage(); }
            final String m = msg;
            h.post(() -> { connecting = false; reconnect.setEnabled(true); info.setText(m); });
        }, "glasses-reconnect").start();
    }

    private void show(Bitmap bm) {
        if (bm == null) return;
        BitmapDrawable d = new BitmapDrawable(getResources(), bm);
        d.setFilterBitmap(false);
        screen.setImageDrawable(d);
        mirrorInfo.setText(L.t("Updated live from the frames sent to the glasses") + " · " + GlassesLink.MIRROR.frames);
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            String st = link.state();
            boolean ready = "READY".equals(st);
            String name = link.name().isEmpty() ? link.lastName() : link.name();
            state.setText((name.isEmpty() ? L.t("Glasses") : name) + " · " + L.t(ready ? "connected" : "not connected"));
            state.setTextColor(ready ? Look.OK : Look.MUTED);
            if (ready && !connecting) {
                new Thread(() -> { int bat = link.battery(); h.post(() -> { if (!connecting) info.setText(bat >= 0 ? L.t("Battery") + " " + bat + " %" : L.t("Battery unknown")); }); }, "glasses-battery").start();
            }
            if (GlassesLink.MIRROR.last() == null) mirrorInfo.setText(L.t("Nothing shown yet: the picture appears as soon as something is sent to the glasses."));
            h.postDelayed(this, 2000);
        }
    };

    @Override public boolean onKeyDown(int code, KeyEvent e) {
        if (prefs.getBoolean("volume_keys", true) && "READY".equals(link.state())) {
            if (code == KeyEvent.KEYCODE_VOLUME_UP) { press("next"); return true; }
            if (code == KeyEvent.KEYCODE_VOLUME_DOWN) { press("back"); return true; }
        }
        return super.onKeyDown(code, e);
    }

    @Override protected void onDestroy() {
        if (viaPc) { super.onDestroy(); return; }
        h.removeCallbacks(tick);
        GlassesLink.MIRROR.setListener(null);
        super.onDestroy();
    }
}
