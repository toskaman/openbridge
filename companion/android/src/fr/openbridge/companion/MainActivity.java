package fr.openbridge.companion;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Large, D-pad friendly screen. The relay runs only while this app is open (no background scanning). */
public class MainActivity extends Activity implements RelayServer.Ui {
    private RelayServer relay;
    private TextView status, code, state;
    private Button permission, enable, unpair;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL); root.setPadding(64, 48, 64, 48); root.setBackgroundColor(Color.rgb(16, 19, 19));
        root.addView(text("OpenBridge Companion", 34, true));
        root.addView(text("Lets OpenBridge on your PC ask this device for a short Bluetooth LE scan. Nothing runs unless you pair and enable it here. No location is used.", 18, false));
        state = text("", 18, false); root.addView(state);
        code = text("", 64, true); code.setTextColor(Color.rgb(244, 153, 101)); code.setGravity(Gravity.CENTER); root.addView(code);
        permission = button("Allow Bluetooth scanning"); enable = button("Enable scans for OpenBridge"); unpair = button("Remove pairing");
        root.addView(permission); root.addView(enable); root.addView(unpair);
        status = text("Starting…", 16, false); root.addView(status);
        ScrollView scroll = new ScrollView(this); scroll.addView(root); setContentView(scroll);
        relay = new RelayServer(this, this);
        permission.setOnClickListener(v -> requestScanPermission());
        enable.setOnClickListener(v -> { relay.setOwnerEnabled(!relay.ownerEnabled()); refresh(); });
        unpair.setOnClickListener(v -> { relay.unpair(); refresh(); });
        permission.requestFocus();
        relay.start(); refresh();
    }

    private void requestScanPermission() {
        if (Build.VERSION.SDK_INT >= 31) requestPermissions(new String[]{"android.permission.BLUETOOTH_SCAN"}, 1);
        else requestPermissions(new String[]{"android.permission.ACCESS_FINE_LOCATION"}, 1);
    }

    @Override public void onRequestPermissionsResult(int r, String[] p, int[] g) { refresh(); }
    @Override protected void onResume() { super.onResume(); refresh(); }
    @Override protected void onDestroy() { relay.stop(); super.onDestroy(); }

    private void refresh() {
        runOnUiThread(() -> {
            boolean ble = relay.bleHardware();
            state.setText("Relay ID: " + relay.relayId() + "\nBluetooth LE hardware: " + (ble ? "yes" : "no (scans unavailable)")
                    + "\nBluetooth: " + (relay.bluetoothOn() ? "on" : "off – turn it on in system settings")
                    + "\nScan permission: " + (relay.scanPermission() ? "granted" : "not granted")
                    + "\nPaired with a PC: " + (relay.paired() ? "yes" : "no") + "\nScans enabled by you: " + (relay.ownerEnabled() ? "yes" : "no"));
            permission.setVisibility(ble && !relay.scanPermission() ? View.VISIBLE : View.GONE);
            enable.setText(relay.ownerEnabled() ? "Disable scans for OpenBridge" : "Enable scans for OpenBridge");
            enable.setEnabled(relay.paired());
            unpair.setEnabled(relay.paired());
        });
    }

    @Override public void status(String text) { runOnUiThread(() -> { status.setText(text); refresh(); }); }
    @Override public void code(String c) { runOnUiThread(() -> code.setText(c == null ? "" : "Pairing code\n" + c)); }

    private TextView text(String s, int size, boolean bold) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(size); t.setTextColor(Color.rgb(240, 238, 229));
        t.setPadding(0, 12, 0, 12); if (bold) t.setTypeface(Typeface.DEFAULT_BOLD); return t;
    }
    private Button button(String s) {
        Button b = new Button(this); b.setText(s); b.setTextSize(22); b.setAllCaps(false); b.setFocusable(true); b.setMinHeight(120); return b;
    }
}
