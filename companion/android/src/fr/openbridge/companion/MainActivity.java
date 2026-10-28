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
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.speech.tts.TextToSpeech;
import java.io.ByteArrayOutputStream;
import java.util.Locale;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
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
    private LinearLayout codeCard, controlsCard, controlsBox;
    private TextView resultText;
    private LinearLayout commandCard;
    private EditText commandInput;
    private TextView commandResult;
    private Button bluetooth, location, permission, enable, unpair;
    private boolean tv;
    private boolean setupRunning;
    private ScrollView scroll;
    private Button setup;
    private static final int VOICE_PERM = 11;
    private static final int VOICE_RATE = 16000, VOICE_MAX_S = 15;
    private AudioRecord recorder;
    private Thread recordThread;
    private volatile boolean recording;
    private Button mic;
    private TextToSpeech tts;

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

        controlsCard = card(); controlsCard.setVisibility(View.GONE);
        controlsCard.addView(text("REMOTE CONTROLS · hold to send", 12, true, MUTED));
        controlsBox = new LinearLayout(this); controlsBox.setOrientation(LinearLayout.VERTICAL); controlsCard.addView(controlsBox);
        resultText = text("", 14, false, OK); controlsCard.addView(resultText);
        root.addView(controlsCard); root.addView(spacer(14));

        commandCard = card(); commandCard.setVisibility(View.GONE);
        commandCard.addView(text("ASK FROM HERE · type or speak, reviewed on your PC", 12, true, MUTED));
        commandInput = new EditText(this); commandInput.setHint("e.g. Start my vacuum");
        commandInput.setTextColor(TEXT); commandInput.setHintTextColor(MUTED);
        commandInput.setTextSize(TypedValue.COMPLEX_UNIT_SP, tv ? 20 : 16);
        commandInput.setSingleLine(true);
        commandCard.addView(commandInput);
        LinearLayout sendRow = new LinearLayout(this); sendRow.setOrientation(LinearLayout.HORIZONTAL);
        Button send = button("Send to PC", true);
        send.setOnClickListener(v -> {
            String s = relay.submitCommand(commandInput.getText().toString());
            commandResult.setText(s);
            if (s != null && s.startsWith("Sent")) commandInput.setText("");
        });
        sendRow.addView(send, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        mic = button("Speak", false);
        mic.setCompoundDrawablesWithIntrinsicBounds(android.R.drawable.ic_btn_speak_now, 0, 0, 0);
        mic.setCompoundDrawablePadding(dp(8));
        mic.setOnClickListener(v -> toggleRecord());
        LinearLayout.LayoutParams micLp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        micLp.leftMargin = dp(10);
        sendRow.addView(mic, micLp);
        commandCard.addView(sendRow);
        commandResult = text("", 14, false, OK); commandCard.addView(commandResult);
        root.addView(commandCard); root.addView(spacer(14));

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
        relay.start(); refresh(); controls(relay.controls());
        try {
            tts = new TextToSpeech(this, status -> {
                if (status != TextToSpeech.SUCCESS) { tts = null; return; }
                int r = tts.setLanguage(Locale.getDefault());
                if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) tts.setLanguage(Locale.ENGLISH);
            });
        } catch (Exception e) { tts = null; }   // no TTS engine: results still show as text
        final android.os.Handler h = new android.os.Handler(getMainLooper());
        h.postDelayed(new Runnable() { @Override public void run() {
            String s = relay.expirePending(); if (s != null) resultText.setText(s);
            renderBusy();
            if (!isFinishing()) h.postDelayed(this, 5000);
        } }, 5000);
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
        if (r == VOICE_PERM) {
            if (granted) startRecord(); else commandResult.setText("Microphone declined — type instead.");
            return;
        }
        if (!granted) setupRunning = false;     // owner declined: stop asking
        refresh(); nextSetupStep();
    }
    @Override protected void onActivityResult(int r, int c, Intent d) {
        if (c != RESULT_OK) setupRunning = false;
        refresh(); nextSetupStep();
    }

    /** Device-side voice: record raw PCM16 here, the PC transcribes with local Meta STT and
        reports back; this device speaks the report. Sound never leaves this flow except to the paired PC. */
    private void toggleRecord() {
        if (recording) { stopRecord(false); return; }
        if (checkSelfPermission("android.permission.RECORD_AUDIO") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.RECORD_AUDIO"}, VOICE_PERM); return;
        }
        startRecord();
    }

    private void startRecord() {
        int min = AudioRecord.getMinBufferSize(VOICE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (min <= 0) { commandResult.setText("Voice recording is not supported on this device."); return; }
        try {
            recorder = new AudioRecord(MediaRecorder.AudioSource.MIC, VOICE_RATE, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT, Math.max(min * 2, VOICE_RATE * 2));
            if (recorder.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("init");
        } catch (Exception e) { commandResult.setText("Microphone unavailable."); recorder = null; return; }
        final int cap = VOICE_RATE * 2 * VOICE_MAX_S;
        final ByteArrayOutputStream pcm = new ByteArrayOutputStream(cap);
        recording = true;
        mic.setText("Stop");
        commandResult.setText("Recording — tap Stop to send (15 s max).");
        recordThread = new Thread(() -> {
            short[] buf = new short[VOICE_RATE / 5];
            byte[] raw = new byte[buf.length * 2];
            try {
                recorder.startRecording();
                while (recording && pcm.size() < cap) {
                    int n = recorder.read(buf, 0, buf.length);
                    if (n <= 0) break;
                    for (int i = 0; i < n; i++) { raw[2 * i] = (byte) buf[i]; raw[2 * i + 1] = (byte) (buf[i] >> 8); }
                    pcm.write(raw, 0, n * 2);
                }
            } catch (Exception ignored) { }
            final byte[] clip = pcm.toByteArray();
            runOnUiThread(() -> stopRecord(clip, pcm.size() >= cap));
        }, "openbridge-voice");
        recordThread.start();
    }

    /** UI-thread stop (tap): the reader thread finishes and queues. Cancel (pause) drops the clip. */
    private boolean dropClip;
    private void stopRecord(boolean cancel) {
        recording = false;
        dropClip = cancel;
        mic.setText("Speak");
        if (cancel) commandResult.setText("Voice cancelled.");
    }

    private void stopRecord(byte[] clip, boolean capped) {
        recording = false;
        releaseRecorder();
        mic.setText("Speak");
        if (dropClip) { dropClip = false; return; }
        if (clip == null || clip.length < 16000) { commandResult.setText("Too short — hold a little longer."); return; }
        String s = relay.submitVoice(clip);
        commandResult.setText((capped ? "15 s limit — " : "") + s);
    }

    private void releaseRecorder() {
        recording = false;
        if (recorder != null) { try { recorder.stop(); } catch (Exception ignored) { } try { recorder.release(); } catch (Exception ignored) { } recorder = null; }
    }
    @Override protected void onResume() { super.onResume(); relay.foreground = true; relay.start(); refresh(); }
    @Override protected void onPause() { if (recording) stopRecord(true); relay.foreground = false; super.onPause(); }
    @Override protected void onDestroy() { releaseRecorder(); if (tts != null) { try { tts.shutdown(); } catch (Exception ignored) { } } super.onDestroy(); }

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
            commandCard.setVisibility(paired ? View.VISIBLE : View.GONE);
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

    /** Controls the owner authorized on the PC; each press sends one request, the PC verifies and reports back. */
    @Override public void controls(org.json.JSONArray c) {
        runOnUiThread(() -> {
            controlsBox.removeAllViews();
            for (int i = 0; i < c.length(); i++) {
                org.json.JSONObject o = c.optJSONObject(i); if (o == null) continue;
                String id = o.optString("control_id");
                Button b = button(o.optString("label"), i == 0);
                b.setTag(new String[]{id, o.optString("label")});
                // Hold to send: a tap does nothing, so stray or phantom touches (watch off the wrist) never send a command.
                final org.json.JSONObject[] down = new org.json.JSONObject[1];
                b.setOnTouchListener((v, e) -> {
                    if (e.getActionMasked() == android.view.MotionEvent.ACTION_DOWN) {
                        try { down[0] = new org.json.JSONObject().put("tool", e.getToolType(0)).put("pressure", Math.round(e.getPressure() * 100) / 100.0)
                                .put("size", Math.round(e.getSize() * 100) / 100.0).put("down_ms", 0).put("t", e.getEventTime()); } catch (Exception ignored) { }
                    }
                    return false;                                   // keep the normal click / long-click handling
                });
                b.setOnClickListener(v -> resultText.setText("Hold the button to send"));
                b.setOnLongClickListener(v -> {
                    org.json.JSONObject touch = down[0];
                    try { if (touch != null) { touch.put("down_ms", android.os.SystemClock.uptimeMillis() - touch.getLong("t")); touch.remove("t"); } } catch (Exception ignored) { }
                    down[0] = null;
                    String s = relay.press(id, touch == null ? "key" : "long_press", touch);
                    if (s != null) resultText.setText(s);
                    renderBusy();                                   // feedback on the button itself: "Sending…", disabled
                    return true;
                });
                controlsBox.addView(b); controlsBox.addView(spacer(8));
            }
            controlsCard.setVisibility(c.length() > 0 ? View.VISIBLE : View.GONE);
        });
    }
    @Override public void result(String text) { runOnUiThread(() -> { resultText.setText(text); renderBusy(); }); }
    @Override public void commandResult(String text) { runOnUiThread(() -> commandResult.setText(text)); }
    /** Voice-originated reports are spoken on this device; typed ones stay silent. */
    @Override public void commandResult(String text, boolean voice) {
        runOnUiThread(() -> {
            commandResult.setText(text);
            if (voice && tts != null && text != null && !text.isEmpty()) {
                try { tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "ob-voice"); }
                catch (Exception ignored) { }
            }
        });
    }

    /** One press in flight per control: the button shows "Sending…" and ignores presses until the PC answers or 20 s pass. */
    private void renderBusy() {
        for (int i = 0; i < controlsBox.getChildCount(); i++) {
            View v = controlsBox.getChildAt(i);
            if (!(v instanceof Button) || !(v.getTag() instanceof String[])) continue;
            String[] tag = (String[]) v.getTag(); boolean busy = relay.busy(tag[0]);
            ((Button) v).setText(busy ? "Sending…" : tag[1]); v.setEnabled(!busy);
        }
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
