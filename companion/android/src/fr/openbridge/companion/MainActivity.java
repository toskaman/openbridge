package fr.openbridge.companion;

import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.view.KeyEvent;

/** Modern, remote-friendly screen. The relay runs only while this app is open (no background scanning). */
public class MainActivity extends Activity implements RelayServer.Ui {
    private static final int BG = Color.rgb(13, 16, 18), CARD = Color.rgb(24, 29, 33), LINE = Color.rgb(48, 56, 62),
            TEXT = Color.rgb(240, 238, 229), MUTED = Color.rgb(154, 165, 163), ACCENT = Color.rgb(244, 153, 101),
            OK = Color.rgb(140, 205, 155), WARN = Color.rgb(240, 184, 130);
    private RelayServer relay;
    private LinearLayout checklist;
    private TextView status, code, codeHint;
    private LinearLayout codeCard;
    private Button bluetooth, location, permission, enable, unpair;
    private boolean tv;
    private boolean setupRunning;
    private ScrollView scroll;
    private Button setup;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        tv = getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK);
        relay = RelayServer.get(this, this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(BG);
        int pad = dp(tv ? 48 : 20); root.setPadding(pad, dp(tv ? 32 : 24), pad, dp(24));

        LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        TextView mark = text("↗", 22, true, BG); mark.setGravity(Gravity.CENTER); mark.setBackground(round(ACCENT, ACCENT, 10));
        header.addView(mark, new LinearLayout.LayoutParams(dp(40), dp(40)));
        LinearLayout titles = new LinearLayout(this); titles.setOrientation(LinearLayout.VERTICAL); titles.setPadding(dp(14), 0, 0, 0);
        titles.addView(text("OpenBridge Companion", tv ? 28 : 22, true, TEXT));
        titles.addView(text("Bluetooth relay for your OpenBridge PC", 14, false, MUTED));
        header.addView(titles); root.addView(header);
        root.addView(spacer(18));

        codeCard = card(); codeCard.setGravity(Gravity.CENTER_HORIZONTAL); codeCard.setVisibility(View.GONE);
        codeHint = text("Enter this code in OpenBridge on your PC", 15, false, MUTED); codeHint.setGravity(Gravity.CENTER);
        code = text("", tv ? 72 : 56, true, ACCENT); code.setGravity(Gravity.CENTER); code.setLetterSpacing(0.15f);
        codeCard.addView(codeHint); codeCard.addView(code); root.addView(codeCard); root.addView(spacer(14));

        LinearLayout statusCard = card();
        statusCard.addView(text("READINESS", 12, true, MUTED));
        checklist = new LinearLayout(this); checklist.setOrientation(LinearLayout.VERTICAL); statusCard.addView(checklist);
        root.addView(statusCard); root.addView(spacer(14));

        setup = button("Set up everything", true);
        root.addView(setup); root.addView(spacer(10));
        bluetooth = button("Turn on Bluetooth", false);
        location = button("Turn on location (needed by Android " + Build.VERSION.RELEASE + ")", false);
        permission = button("Allow Bluetooth scanning", false);
        enable = button("Pause scans", false);
        unpair = button("Remove pairing", false);
        for (Button x : new Button[]{bluetooth, location, permission, enable, unpair}) { root.addView(x); root.addView(spacer(10)); }

        status = text("Starting…", 14, false, MUTED); root.addView(status);
        root.addView(text("Scans run only while this app is open, only on a signed request from your paired PC, and never use location data.", 13, false, MUTED));

        scroll = new ScrollView(this); scroll.setBackgroundColor(BG); scroll.addView(root); setContentView(scroll);
        setup.setOnClickListener(v -> { setupRunning = true; nextSetupStep(); });
        bluetooth.setOnClickListener(v -> turnOnBluetooth());
        location.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)));
        permission.setOnClickListener(v -> requestScanPermission());
        enable.setOnClickListener(v -> { relay.setOwnerEnabled(!relay.ownerEnabled()); refresh(); });
        unpair.setOnClickListener(v -> { relay.unpair(); refresh(); });
        relay.start(); refresh();
        if (!getSharedPreferences("ui", MODE_PRIVATE).getBoolean("setup_offered", false)) {
            getSharedPreferences("ui", MODE_PRIVATE).edit().putBoolean("setup_offered", true).apply();
            setupRunning = true; nextSetupStep();      // first launch: walk through the system dialogs once
        }
    }

    /** Each step opens an Android system dialog or settings screen; Android always asks the owner. */
    private void nextSetupStep() {
        if (!setupRunning) return;
        if (!relay.bleHardware()) { setupRunning = false; refresh(); return; }
        if (!relay.scanPermission()) { requestScanPermission(); return; }
        if (!relay.bluetoothOn()) { turnOnBluetooth(); return; }
        if (!relay.locationOn()) { setupRunning = false; startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)); return; }
        setupRunning = false; refresh();
    }

    @SuppressWarnings("deprecation")
    private void turnOnBluetooth() {
        if (!relay.bluetoothServiceEnabled()) {
            setupRunning = false; status("The system Bluetooth app is disabled on this device. Re-enable it in Settings > Apps > See all apps > Show system apps > Bluetooth.");
            Intent apps = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:com.android.bluetooth"));
            if (apps.resolveActivity(getPackageManager()) != null) startActivity(apps);
            return;
        }
        BluetoothAdapter a = ((android.bluetooth.BluetoothManager) getSystemService(BLUETOOTH_SERVICE)).getAdapter();
        if (a == null) { status("No Bluetooth adapter on this device."); return; }
        if (Build.VERSION.SDK_INT < 33) {
            // Owner tapped the button: documented direct enable (Android 12 and older), no extra screen.
            if (Build.VERSION.SDK_INT >= 31 && checkSelfPermission("android.permission.BLUETOOTH_CONNECT") != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{"android.permission.BLUETOOTH_CONNECT"}, 2); return;
            }
            try {
                if (a.enable()) { status("Turning Bluetooth on…"); new android.os.Handler(getMainLooper()).postDelayed(() -> { refresh(); nextSetupStep(); }, 2500); return; }
            } catch (SecurityException ignored) { }
        }
        if (Build.VERSION.SDK_INT >= 31 && checkSelfPermission("android.permission.BLUETOOTH_CONNECT") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.BLUETOOTH_CONNECT"}, 2); return;
        }
        Intent ask = new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE);       // Android 13+: system dialog, owner decides
        if (ask.resolveActivity(getPackageManager()) != null) { startActivityForResult(ask, 3); return; }
        Intent settings = new Intent(Settings.ACTION_BLUETOOTH_SETTINGS);
        if (settings.resolveActivity(getPackageManager()) != null) { setupRunning = false; startActivity(settings); return; }
        setupRunning = false;
        status(tv ? "Turn Bluetooth on in Settings > Remotes & Accessories, then come back." : "Turn Bluetooth on from the quick settings panel, then come back.");
    }

    private void requestScanPermission() {
        String perm = Build.VERSION.SDK_INT >= 31 ? "android.permission.BLUETOOTH_SCAN" : "android.permission.ACCESS_FINE_LOCATION";
        android.content.SharedPreferences ui = getSharedPreferences("ui", MODE_PRIVATE);
        if (ui.getBoolean("asked_" + perm, false) && !shouldShowRequestPermissionRationale(perm)) {
            // Android will not show the dialog again ("Don't ask again"): open this app's permission page instead.
            status("Android blocked the request dialog. Allow the permission on the page that just opened.");
            startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:" + getPackageName())));
            setupRunning = false; return;
        }
        ui.edit().putBoolean("asked_" + perm, true).apply();
        requestPermissions(new String[]{perm}, 1);
    }

    @Override public void onRequestPermissionsResult(int r, String[] p, int[] g) {
        boolean granted = g.length > 0 && g[0] == PackageManager.PERMISSION_GRANTED;
        if (r == 2 && granted) { turnOnBluetooth(); return; }
        if (!granted) setupRunning = false;     // owner declined: stop asking
        refresh(); nextSetupStep();
    }
    @Override protected void onActivityResult(int r, int c, Intent d) {
        if (c != RESULT_OK) setupRunning = false;
        refresh(); nextSetupStep();
    }
    @Override protected void onResume() { super.onResume(); relay.foreground = true; relay.start(); refresh(); }
    @Override protected void onPause() { relay.foreground = false; super.onPause(); }

    private void refresh() {
        runOnUiThread(() -> {
            boolean ble = relay.bleHardware(), on = relay.bluetoothOn(), loc = relay.locationOn(), perm = relay.scanPermission(),
                    paired = relay.paired(), enabled = relay.ownerEnabled();
            checklist.removeAllViews();
            row("Bluetooth LE hardware", ble, ble ? "Available" : "Not present on this device");
            boolean service = relay.bluetoothServiceEnabled();
            if (!service) row("System Bluetooth app", false, "Disabled – re-enable it in Settings > Apps > System apps > Bluetooth");
            row("Bluetooth", on, on ? "On" : "Off");
            if (Build.VERSION.SDK_INT < 31) row("Location services", loc, loc ? "On" : "Off (required by Android 11 and older)");
            row("Scan permission", perm, perm ? "Granted" : "Not granted yet");
            row("Paired with a PC", paired, paired ? "Yes" : "Not yet");
            if (paired) row("Scans", enabled, enabled ? "Available while this app is open" : "Paused by you");
            boolean ready = !ble || (on && loc && perm);
            setup.setVisibility(ble && !ready ? View.VISIBLE : View.GONE);
            setup.setText("Set up everything");
            bluetooth.setVisibility(ble && !on ? View.VISIBLE : View.GONE);
            location.setVisibility(ble && !loc ? View.VISIBLE : View.GONE);
            permission.setVisibility(ble && !perm ? View.VISIBLE : View.GONE);
            enable.setText(enabled ? "Pause scans" : "Resume scans");
            enable.setVisibility(paired ? View.VISIBLE : View.GONE);
            unpair.setVisibility(paired ? View.VISIBLE : View.GONE);
            View first = setup.getVisibility() == View.VISIBLE ? setup : bluetooth.getVisibility() == View.VISIBLE ? bluetooth : location.getVisibility() == View.VISIBLE ? location
                    : permission.getVisibility() == View.VISIBLE ? permission : enable.getVisibility() == View.VISIBLE ? enable : null;
            if (first != null && getCurrentFocus() == null) first.requestFocus();
        });
    }

    private void row(String label, boolean ok, String value) {
        LinearLayout r = new LinearLayout(this); r.setGravity(Gravity.CENTER_VERTICAL); r.setPadding(0, dp(10), 0, dp(10));
        TextView dot = text(ok ? "✓" : "!", 15, true, ok ? OK : WARN); dot.setGravity(Gravity.CENTER);
        dot.setBackground(round(Color.argb(40, Color.red(ok ? OK : WARN), Color.green(ok ? OK : WARN), Color.blue(ok ? OK : WARN)), Color.TRANSPARENT, 14));
        r.addView(dot, new LinearLayout.LayoutParams(dp(28), dp(28)));
        TextView l = text(label, 16, false, TEXT); l.setPadding(dp(12), 0, 0, 0);
        r.addView(l, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        r.addView(text(value, 14, false, ok ? MUTED : WARN));
        checklist.addView(r);
    }

    @Override public void status(String text) { runOnUiThread(() -> { status.setText(text); refresh(); }); }
    @Override public void code(String c) {
        runOnUiThread(() -> {
            codeCard.setVisibility(c == null ? View.GONE : View.VISIBLE);
            code.setText(c == null ? "" : c.substring(0, 3) + " " + c.substring(3));
            code.setContentDescription(c == null ? null : "Pairing code " + c);
            if (c != null) scroll.post(() -> scroll.fullScroll(View.FOCUS_UP));     // make sure the code is on screen (TV)
        });
    }

    private LinearLayout card() {
        LinearLayout c = new LinearLayout(this); c.setOrientation(LinearLayout.VERTICAL); c.setPadding(dp(20), dp(18), dp(20), dp(18));
        c.setBackground(round(CARD, LINE, 16)); return c;
    }
    private Button button(String s, boolean primary) {
        Button b = new Button(this); b.setText(s); b.setAllCaps(false); b.setTextSize(tv ? 20 : 17); b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setTextColor(primary ? BG : TEXT); b.setMinHeight(dp(tv ? 64 : 54)); b.setFocusable(true); b.setStateListAnimator(null);
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focused = round(primary ? Color.rgb(255, 178, 134) : Color.rgb(44, 64, 82), Color.WHITE, 14); focused.setStroke(dp(3), Color.WHITE);
        states.addState(new int[]{android.R.attr.state_focused}, focused);
        states.addState(new int[]{android.R.attr.state_pressed}, round(primary ? Color.rgb(255, 178, 134) : Color.rgb(44, 64, 82), LINE, 14));
        states.addState(new int[]{}, round(primary ? ACCENT : CARD, primary ? ACCENT : LINE, 14));
        b.setBackground(states); return b;
    }
    private GradientDrawable round(int fill, int stroke, int radiusDp) {
        GradientDrawable d = new GradientDrawable(); d.setColor(fill); d.setCornerRadius(dp(radiusDp)); d.setStroke(dp(1), stroke); return d;
    }
    private TextView text(String s, int size, boolean bold, int color) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(TypedValue.COMPLEX_UNIT_SP, size); t.setTextColor(color);
        t.setLineSpacing(0, 1.15f); if (bold) t.setTypeface(Typeface.DEFAULT_BOLD); return t;
    }
    private View spacer(int h) { View v = new View(this); v.setLayoutParams(new LinearLayout.LayoutParams(1, dp(h))); return v; }
    private int dp(int v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics())); }
}
