package fr.openbridge.companion;

import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Locale;

/**
 * Voice-first companion screen: a living 3D orb reacts to the mic, to speech and to every relay event;
 * typing, live state, controls and setup sit underneath. The relay runs only while this app is open.
 */
public class MainActivity extends Activity implements RelayServer.Ui {
    // ---- palette -------------------------------------------------------------------------------------
    private static final int BG_TOP = Color.rgb(3, 5, 14), BG_BOTTOM = Color.rgb(12, 10, 30),
            GLASS = Color.argb(20, 255, 255, 255), GLASS_HI = Color.argb(34, 255, 255, 255), GLASS_LINE = Color.argb(36, 255, 255, 255),
            TEXT = Color.rgb(236, 240, 255), MUTED = Color.rgb(138, 148, 182), FAINT = Color.rgb(92, 100, 132),
            CYAN = Color.rgb(0, 229, 255), VIOLET = Color.rgb(140, 100, 255), MAGENTA = Color.rgb(255, 79, 216),
            OK = Color.rgb(105, 240, 174), WARN = Color.rgb(255, 183, 77), INK = Color.rgb(6, 8, 18);

    private RelayServer relay;
    private boolean tv;

    // Voice presence
    private VoiceOrbView orb;
    private TextView stateLabel, caption, chip;
    // Input
    private EditText commandInput;
    private GlyphButton mic, send;
    private TextView commandResult;
    // Pairing
    private LinearLayout codeCard;
    private TextView code;
    // Controls
    private LinearLayout controlsCard, controlsBox;
    private TextView resultText;
    // Live info
    private TextView linkValue, linkDot, btValue, btDot, scanValue, scanDot, ctrlValue, ctrlDot, deviceLine;
    private LinearLayout feed;
    private final ArrayDeque<String[]> events = new ArrayDeque<>();
    // System
    private LinearLayout systemBody, checklist;
    private TextView systemToggle, statusLine;
    private boolean systemOpen, systemTouched;
    private Button setup, bluetooth, location, permission, enable, unpair, fullctl;
    private boolean setupRunning;
    private ScrollView scroll;

    // Live state that drives the orb
    private volatile boolean speaking;
    private boolean codeShown, scanning, relayFailed;
    private long thinkingUntil;

    // Voice capture
    private static final int VOICE_PERM = 11;
    private static final int VOICE_RATE = 16000, VOICE_MAX_S = 15;
    private AudioRecord recorder;
    private Thread recordThread;
    private volatile boolean recording;
    private TextToSpeech tts;
    private final Handler h = new Handler(android.os.Looper.getMainLooper());

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        tv = getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK);
        relay = RelayServer.get(this, this);
        getWindow().setStatusBarColor(BG_TOP);
        getWindow().setNavigationBarColor(BG_BOTTOM);

        // ---- presence: header + orb + state + caption --------------------------------------------------
        LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout titles = new LinearLayout(this); titles.setOrientation(LinearLayout.VERTICAL);
        TextView brand = text("OPENBRIDGE", 11, true, CYAN); brand.setLetterSpacing(0.35f);
        titles.addView(brand);
        titles.addView(text("Companion", tv ? 26 : 22, false, TEXT, "sans-serif-light"));
        header.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        chip = text("", 12, true, MUTED); chip.setPadding(dp(12), dp(6), dp(14), dp(6)); chip.setLetterSpacing(0.08f);
        header.addView(chip);

        orb = new VoiceOrbView(this);
        orb.setOnClickListener(v -> toggleRecord());          // tap the orb to talk
        orb.setFocusable(false);

        stateLabel = text("", 12, true, CYAN); stateLabel.setGravity(Gravity.CENTER); stateLabel.setLetterSpacing(0.4f);
        caption = text("", tv ? 24 : 20, false, TEXT, "sans-serif-light"); caption.setGravity(Gravity.CENTER);
        caption.setLineSpacing(0, 1.2f); caption.setPadding(dp(8), dp(6), dp(8), 0); caption.setMaxLines(4);

        // ---- input bar -------------------------------------------------------------------------------
        LinearLayout bar = new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(18), dp(6), dp(6), dp(6)); bar.setBackground(round(GLASS_HI, GLASS_LINE, 32));
        commandInput = new EditText(this); commandInput.setHint("Ask OpenBridge…  e.g. Start my vacuum");
        commandInput.setTextColor(TEXT); commandInput.setHintTextColor(FAINT); commandInput.setBackground(null);
        commandInput.setTextSize(TypedValue.COMPLEX_UNIT_SP, tv ? 19 : 16); commandInput.setSingleLine(true);
        commandInput.setImeOptions(EditorInfo.IME_ACTION_SEND);
        commandInput.setOnEditorActionListener((v, id, e) -> {
            if (id == EditorInfo.IME_ACTION_SEND || (e != null && e.getKeyCode() == KeyEvent.KEYCODE_ENTER && e.getAction() == KeyEvent.ACTION_DOWN)) { sendCommand(); return true; }
            return false;
        });
        commandInput.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int c, int d) { }
            @Override public void onTextChanged(CharSequence s, int a, int c, int d) { orb.bump(0.22f); }
            @Override public void afterTextChanged(Editable s) { send.setActive(s.toString().trim().length() > 0); }
        });
        bar.addView(commandInput, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        int gs = dp(tv ? 56 : 48);
        mic = new GlyphButton(this, GlyphButton.MIC, MAGENTA);
        mic.setOnClickListener(v -> toggleRecord());
        LinearLayout.LayoutParams micLp = new LinearLayout.LayoutParams(gs, gs); micLp.leftMargin = dp(6);
        bar.addView(mic, micLp);
        send = new GlyphButton(this, GlyphButton.SEND, CYAN);
        send.setOnClickListener(v -> sendCommand());
        LinearLayout.LayoutParams sendLp = new LinearLayout.LayoutParams(gs, gs); sendLp.leftMargin = dp(6);
        bar.addView(send, sendLp);
        commandResult = text("", 13, false, MUTED); commandResult.setGravity(Gravity.CENTER); commandResult.setPadding(0, dp(8), 0, 0);

        // ---- pairing code ----------------------------------------------------------------------------
        codeCard = card(); codeCard.setGravity(Gravity.CENTER_HORIZONTAL); codeCard.setVisibility(View.GONE);
        codeCard.setBackground(round(Color.argb(30, 255, 183, 77), Color.argb(120, 255, 183, 77), 22));
        TextView codeHint = text("ENTER THIS CODE IN OPENBRIDGE ON YOUR PC", 11, true, WARN); codeHint.setGravity(Gravity.CENTER); codeHint.setLetterSpacing(0.2f);
        code = text("", tv ? 64 : 52, false, TEXT, "sans-serif-thin"); code.setGravity(Gravity.CENTER); code.setLetterSpacing(0.18f);
        codeCard.addView(codeHint); codeCard.addView(code);

        // ---- controls --------------------------------------------------------------------------------
        controlsCard = card(); controlsCard.setVisibility(View.GONE);
        controlsCard.addView(sectionTitle("QUICK CONTROLS", "hold to send"));
        controlsBox = new LinearLayout(this); controlsBox.setOrientation(LinearLayout.VERTICAL); controlsCard.addView(controlsBox);
        resultText = text("", 13, false, OK); resultText.setPadding(dp(2), dp(4), 0, 0); controlsCard.addView(resultText);

        // ---- live info -------------------------------------------------------------------------------
        LinearLayout live = card();
        live.addView(sectionTitle("LIVE", null));
        LinearLayout r1 = new LinearLayout(this), r2 = new LinearLayout(this);
        TextView[] t;
        t = tile(r1, "LINK"); linkValue = t[0]; linkDot = t[1];
        t = tile(r1, "BLUETOOTH"); btValue = t[0]; btDot = t[1];
        t = tile(r2, "SCANS"); scanValue = t[0]; scanDot = t[1];
        t = tile(r2, "CONTROLS"); ctrlValue = t[0]; ctrlDot = t[1];
        live.addView(r1); live.addView(spacer(8)); live.addView(r2);
        deviceLine = text("", 12, false, FAINT); deviceLine.setPadding(dp(2), dp(12), 0, 0); live.addView(deviceLine);

        LinearLayout activity = card();
        activity.addView(sectionTitle("ACTIVITY", null));
        feed = new LinearLayout(this); feed.setOrientation(LinearLayout.VERTICAL); activity.addView(feed);

        // ---- system & permissions (collapsible) ------------------------------------------------------
        LinearLayout system = card();
        LinearLayout sysHead = new LinearLayout(this); sysHead.setGravity(Gravity.CENTER_VERTICAL);
        sysHead.setFocusable(true); sysHead.setClickable(true); sysHead.setPadding(0, dp(2), 0, dp(2));
        sysHead.setBackground(focusOnly(14));
        TextView sysTitle = text("SYSTEM & PERMISSIONS", 11, true, MUTED); sysTitle.setLetterSpacing(0.2f);
        sysHead.addView(sysTitle, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        systemToggle = text("Show", 13, true, CYAN); sysHead.addView(systemToggle);
        sysHead.setOnClickListener(v -> { systemTouched = true; systemOpen = !systemOpen; renderSystem(); });
        system.addView(sysHead);
        systemBody = new LinearLayout(this); systemBody.setOrientation(LinearLayout.VERTICAL);
        checklist = new LinearLayout(this); checklist.setOrientation(LinearLayout.VERTICAL); systemBody.addView(checklist);
        systemBody.addView(spacer(8));
        setup = button("Set up everything", true);
        bluetooth = button("Turn on Bluetooth", false);
        location = button("Turn on location (needed by Android " + Build.VERSION.RELEASE + ")", false);
        permission = button("Allow Bluetooth scanning", false);
        enable = button("Pause scans", false);
        unpair = button("Remove pairing", false);
        fullctl = button("Allow full control", false);
        for (Button x : new Button[]{setup, bluetooth, location, permission, enable, fullctl, unpair}) { systemBody.addView(x); systemBody.addView(spacer(8)); }
        statusLine = text("Starting…", 12, false, FAINT); systemBody.addView(statusLine);
        system.addView(systemBody);

        TextView footer = text("Scans run only while this app is open, only on a signed request from your paired PC, and never use location data. "
                + "Voice is sent only to your paired PC.", 12, false, FAINT);
        footer.setPadding(dp(4), dp(4), dp(4), 0);

        // ---- assemble --------------------------------------------------------------------------------
        int pad = dp(tv ? 40 : 18);
        LinearLayout info = new LinearLayout(this); info.setOrientation(LinearLayout.VERTICAL);
        if (tv) {
            LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.HORIZONTAL);
            root.setBackground(bg()); root.setPadding(pad, dp(28), pad, dp(24));
            LinearLayout left = new LinearLayout(this); left.setOrientation(LinearLayout.VERTICAL);
            left.addView(header);
            left.addView(orb, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
            left.addView(stateLabel); left.addView(caption); left.addView(spacer(18));
            left.addView(bar); left.addView(commandResult);
            root.addView(left, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1.15f));
            for (View v : new View[]{codeCard, controlsCard, live, activity, system, footer}) { info.addView(v); info.addView(spacer(14)); }
            scroll = new ScrollView(this); scroll.setVerticalScrollBarEnabled(false); scroll.addView(info);
            LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1); rl.leftMargin = dp(32);
            root.addView(scroll, rl);
            setContentView(root);
        } else {
            info.setPadding(pad, dp(20), pad, dp(28));
            info.addView(header);
            int orbH = Math.min(dp(360), Math.round(getResources().getDisplayMetrics().heightPixels * 0.42f));
            FrameLayout orbBox = new FrameLayout(this);
            orbBox.addView(orb, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, orbH));
            info.addView(orbBox, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, orbH));
            info.addView(stateLabel); info.addView(caption); info.addView(spacer(20));
            info.addView(bar); info.addView(commandResult); info.addView(spacer(18));
            for (View v : new View[]{codeCard, controlsCard, live, activity, system, footer}) { info.addView(v); info.addView(spacer(14)); }
            scroll = new ScrollView(this); scroll.setBackground(bg()); scroll.setVerticalScrollBarEnabled(false); scroll.addView(info);
            setContentView(scroll);
        }

        setup.setOnClickListener(v -> { setupRunning = true; nextSetupStep(); });
        bluetooth.setOnClickListener(v -> turnOnBluetooth());
        location.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)));
        permission.setOnClickListener(v -> requestScanPermission());
        enable.setOnClickListener(v -> { relay.setOwnerEnabled(!relay.ownerEnabled()); log(relay.ownerEnabled() ? "Scans resumed" : "Scans paused by you"); refresh(); });
        unpair.setOnClickListener(v -> { relay.unpair(); refresh(); });
        fullctl.setOnClickListener(v -> toggleFullControl());

        relay.start(); refresh(); controls(relay.controls());
        setCaption(relay.paired() ? "Hi. Ask me anything — type, or tap the orb to talk." : "Open OpenBridge on your PC to pair this device.");
        log("Companion started");
        try {
            tts = new TextToSpeech(this, st -> {
                if (st != TextToSpeech.SUCCESS) { tts = null; return; }
                int r = tts.setLanguage(Locale.getDefault());
                if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) tts.setLanguage(Locale.ENGLISH);
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { speaking = true; runOnUiThread(MainActivity.this::updateOrb); }
                    @Override public void onDone(String id) { speaking = false; runOnUiThread(MainActivity.this::updateOrb); }
                    @Override public void onError(String id) { speaking = false; runOnUiThread(MainActivity.this::updateOrb); }
                    @Override public void onStop(String id, boolean interrupted) { speaking = false; runOnUiThread(MainActivity.this::updateOrb); }
                    @Override public void onRangeStart(String id, int start, int end, int frame) { orb.bump(0.55f + Math.min(0.4f, (end - start) * 0.05f)); }
                });
            });
        } catch (Exception e) { tts = null; }   // no TTS engine: results still show as text
        h.postDelayed(new Runnable() {
            int tick;
            @Override public void run() {
                if (++tick % 5 == 0) { String s = relay.expirePending(); if (s != null) { resultText.setText(s); log(s); orb.pulse(); } renderBusy(); }
                updateOrb();
                if (!isFinishing()) h.postDelayed(this, 1000);
            }
        }, 1000);
        if (!getSharedPreferences("ui", MODE_PRIVATE).getBoolean("setup_offered", false)) {
            getSharedPreferences("ui", MODE_PRIVATE).edit().putBoolean("setup_offered", true).apply();
            setupRunning = true; nextSetupStep();      // first launch: walk through the system dialogs once
        }
    }

    // =================================================================================================
    // Orb state
    // =================================================================================================
    private void updateOrb() {
        int s; String label; int color;
        boolean thinking = System.currentTimeMillis() < thinkingUntil;
        if (recording) { s = VoiceOrbView.LISTENING; label = "LISTENING"; color = CYAN; }
        else if (speaking) { s = VoiceOrbView.SPEAKING; label = "SPEAKING"; color = MAGENTA; }
        else if (thinking || scanning) { s = VoiceOrbView.THINKING; label = scanning && !thinking ? "SCANNING NEARBY" : "THINKING"; color = VIOLET; }
        else if (codeShown) { s = VoiceOrbView.ALERT; label = "PAIRING"; color = WARN; }
        else if (relayFailed) { s = VoiceOrbView.OFFLINE; label = "OFFLINE"; color = MUTED; }
        else { s = VoiceOrbView.IDLE; label = relay.paired() ? "READY" : "WAITING FOR YOUR PC"; color = relay.paired() ? CYAN : MUTED; }
        orb.setState(s);
        stateLabel.setText(label); stateLabel.setTextColor(color);
        mic.setGlyph(recording ? GlyphButton.STOP : GlyphButton.MIC); mic.setActive(recording);
        if (!thinking) thinkingUntil = 0;
    }

    private void setCaption(String s) {
        if (s == null || s.equals(caption.getText().toString())) return;
        caption.animate().cancel();
        caption.animate().alpha(0f).translationY(dp(6)).setDuration(140).withEndAction(() -> {
            caption.setText(s); caption.setTranslationY(-dp(6));
            caption.animate().alpha(1f).translationY(0).setDuration(260).start();
        }).start();
    }

    /** Activity feed, newest first, 6 rows. */
    private void log(String msg) {
        if (msg == null || msg.isEmpty()) return;
        runOnUiThread(() -> {
            String[] top = events.peekFirst();
            if (top != null && top[1].equals(msg)) return;
            events.addFirst(new String[]{new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date()), msg});
            while (events.size() > 6) events.removeLast();
            feed.removeAllViews();
            int i = 0;
            for (String[] e : events) {
                LinearLayout row = new LinearLayout(this); row.setPadding(0, dp(7), 0, dp(7));
                View bead = new View(this); bead.setBackground(round(i == 0 ? CYAN : Color.argb(90, 140, 150, 190), Color.TRANSPARENT, 4));
                LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(dp(6), dp(6)); bl.topMargin = dp(7); bl.rightMargin = dp(12);
                row.addView(bead, bl);
                TextView time = text(e[0], 12, false, FAINT, "monospace"); time.setPadding(0, 0, dp(12), 0);
                row.addView(time);
                row.addView(text(e[1], 13, false, i == 0 ? TEXT : MUTED), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
                feed.addView(row); i++;
            }
        });
    }

    // =================================================================================================
    // Typed and spoken commands
    // =================================================================================================
    private void sendCommand() {
        String typed = commandInput.getText().toString().trim();
        String s = relay.submitCommand(typed);
        commandResult.setText(s);
        if (s != null && s.startsWith("Sent")) {
            commandInput.setText("");
            setCaption("“" + typed + "”");
            log("You: " + typed);
            thinkingUntil = System.currentTimeMillis() + 25_000;
            orb.pulse(); updateOrb();
        }
    }

    /** Device-side voice: record raw PCM16 here, the PC transcribes with local Meta STT and
        reports back; this device speaks the report. Sound never leaves this flow except to the paired PC. */
    private void toggleRecord() {
        if (recording) { stopRecord(false); return; }
        if (!relay.paired()) { commandResult.setText("Pair with your PC first."); orb.pulse(); return; }
        if (tts != null && speaking) { try { tts.stop(); } catch (Exception ignored) { } speaking = false; }
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
        updateOrb();
        setCaption("I'm listening…");
        commandResult.setText("Tap the orb or Stop to send (15 s max).");
        recordThread = new Thread(() -> {
            short[] buf = new short[VOICE_RATE / 20];              // 50 ms chunks: the orb follows your voice closely
            byte[] raw = new byte[buf.length * 2];
            try {
                recorder.startRecording();
                while (recording && pcm.size() < cap) {
                    int n = recorder.read(buf, 0, buf.length);
                    if (n <= 0) break;
                    double sum = 0;
                    for (int i = 0; i < n; i++) { raw[2 * i] = (byte) buf[i]; raw[2 * i + 1] = (byte) (buf[i] >> 8); sum += (double) buf[i] * buf[i]; }
                    pcm.write(raw, 0, n * 2);
                    double rms = Math.sqrt(sum / n) / 32768.0;
                    double db = 20 * Math.log10(Math.max(rms, 1e-6));    // ~ -55 dB silence .. -10 dB loud speech
                    orb.setLevel((float) Math.max(0, Math.min(1, (db + 55) / 42)));
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
        updateOrb();
        if (cancel) commandResult.setText("Voice cancelled.");
    }

    private void stopRecord(byte[] clip, boolean capped) {
        recording = false;
        releaseRecorder();
        updateOrb();
        if (dropClip) { dropClip = false; return; }
        if (clip == null || clip.length < 16000) { commandResult.setText("Too short — hold a little longer."); setCaption("I didn't catch that."); return; }
        String s = relay.submitVoice(clip);
        commandResult.setText((capped ? "15 s limit — " : "") + s);
        if (s != null && s.startsWith("Sent")) {
            log("You spoke (" + (clip.length / (VOICE_RATE * 2)) + " s)");
            setCaption("Got it — working on it…");
            thinkingUntil = System.currentTimeMillis() + 25_000;
            orb.pulse(); updateOrb();
        }
    }

    private void releaseRecorder() {
        recording = false;
        if (recorder != null) { try { recorder.stop(); } catch (Exception ignored) { } try { recorder.release(); } catch (Exception ignored) { } recorder = null; }
    }

    // =================================================================================================
    // Setup flow (unchanged behaviour: every step is an Android system dialog the owner answers)
    // =================================================================================================
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
                if (a.enable()) { status("Turning Bluetooth on…"); h.postDelayed(() -> { refresh(); nextSetupStep(); }, 2500); return; }
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

    /** Standing consent for PC-initiated control. Turning it on shows a warning first; turning it off is instant. */
    private void toggleFullControl() {
        if (relay.fullControl()) { relay.setFullControl(false); log("Full control revoked on this device"); refresh(); return; }
        new android.app.AlertDialog.Builder(this)
                .setTitle("Allow full control?")
                .setMessage("OpenBridge on your PC will be able to send ALL commands to this device's controls without asking you each time. Only allow this on your own devices. You can revoke it here at any moment.")
                .setNegativeButton("Cancel", (d, w) -> { })
                .setPositiveButton("Allow", (d, w) -> { relay.setFullControl(true); log("Full control allowed on this device"); orb.pulse(); refresh(); })
                .show();
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

    @Override protected void onResume() { super.onResume(); relay.foreground = true; relay.start(); refresh(); }
    @Override protected void onPause() { if (recording) stopRecord(true); relay.foreground = false; super.onPause(); }
    @Override protected void onDestroy() { h.removeCallbacksAndMessages(null); releaseRecorder(); if (tts != null) { try { tts.shutdown(); } catch (Exception ignored) { } } super.onDestroy(); }

    // =================================================================================================
    // Live state
    // =================================================================================================
    private void refresh() {
        runOnUiThread(() -> {
            boolean ble = relay.bleHardware(), on = relay.bluetoothOn(), loc = relay.locationOn(), perm = relay.scanPermission(),
                    paired = relay.paired(), enabled = relay.ownerEnabled();

            // Header chip
            String chipText = paired ? "PAIRED" : codeShown ? "PAIRING" : "NOT PAIRED";
            int chipColor = paired ? OK : codeShown ? WARN : MUTED;
            chip.setText("●  " + chipText); chip.setTextColor(chipColor);
            chip.setBackground(round(Color.argb(28, Color.red(chipColor), Color.green(chipColor), Color.blue(chipColor)),
                    Color.argb(90, Color.red(chipColor), Color.green(chipColor), Color.blue(chipColor)), 20));

            // Live tiles
            setTile(linkValue, linkDot, paired ? "Paired" : codeShown ? "Pairing…" : relayFailed ? "Offline" : "Not paired",
                    paired ? OK : codeShown ? WARN : relayFailed ? WARN : MUTED);
            setTile(btValue, btDot, !ble ? "No BLE" : on ? "On" : "Off", !ble ? MUTED : on ? OK : WARN);
            setTile(scanValue, scanDot, !paired || !ble ? "—" : scanning ? "Scanning" : enabled ? "Allowed" : "Paused",
                    scanning ? VIOLET : paired && ble && enabled ? OK : MUTED);
            int n = relay.controls().length();
            setTile(ctrlValue, ctrlDot, n == 0 ? "None" : n + (n == 1 ? " control" : " controls"), n > 0 ? CYAN : MUTED);
            String id = relay.relayId();
            deviceLine.setText((tv ? "Android TV" : "Phone") + " · Android " + Build.VERSION.RELEASE + " · " + id.substring(0, Math.min(14, id.length())) + " · port " + RelayServer.PORT);

            // Checklist
            checklist.removeAllViews();
            row("Bluetooth LE hardware", ble, ble ? "Available" : "Not present");
            if (!relay.bluetoothServiceEnabled()) row("System Bluetooth app", false, "Disabled in Settings");
            row("Bluetooth", on, on ? "On" : "Off");
            if (Build.VERSION.SDK_INT < 31) row("Location services", loc, loc ? "On" : "Off (Android 11 and older)");
            row("Scan permission", perm, perm ? "Granted" : "Not granted yet");
            row("Paired with a PC", paired, paired ? "Yes" : "Not yet");
            if (paired) row("Scans", enabled, enabled ? "While this app is open" : "Paused by you");
            if (paired) row("Full control", relay.fullControl(), relay.fullControl() ? "Allowed — the PC may act without asking" : "Off");
            boolean ready = !ble || (on && loc && perm);
            setup.setVisibility(ble && !ready ? View.VISIBLE : View.GONE);
            bluetooth.setVisibility(ble && !on ? View.VISIBLE : View.GONE);
            location.setVisibility(ble && !loc ? View.VISIBLE : View.GONE);
            permission.setVisibility(ble && !perm ? View.VISIBLE : View.GONE);
            enable.setText(enabled ? "Pause scans" : "Resume scans");
            enable.setVisibility(paired ? View.VISIBLE : View.GONE);
            fullctl.setText(relay.fullControl() ? "Revoke full control" : "Allow full control");
            fullctl.setVisibility(paired ? View.VISIBLE : View.GONE);
            unpair.setVisibility(paired ? View.VISIBLE : View.GONE);
            if (!systemTouched) systemOpen = !ready || !paired;
            renderSystem();
            updateOrb();

            View first = setup.getVisibility() == View.VISIBLE ? setup : bluetooth.getVisibility() == View.VISIBLE ? bluetooth : location.getVisibility() == View.VISIBLE ? location
                    : permission.getVisibility() == View.VISIBLE ? permission : null;
            if (first == null && paired) first = commandInput;
            if (first != null && getCurrentFocus() == null && tv) first.requestFocus();
        });
    }

    private void renderSystem() {
        systemBody.setVisibility(systemOpen ? View.VISIBLE : View.GONE);
        systemToggle.setText(systemOpen ? "Hide" : "Show");
    }

    private void row(String label, boolean ok, String value) {
        LinearLayout r = new LinearLayout(this); r.setGravity(Gravity.CENTER_VERTICAL); r.setPadding(0, dp(8), 0, dp(8));
        int c = ok ? OK : WARN;
        TextView dot = text(ok ? "✓" : "!", 13, true, c); dot.setGravity(Gravity.CENTER);
        dot.setBackground(round(Color.argb(36, Color.red(c), Color.green(c), Color.blue(c)), Color.TRANSPARENT, 12));
        r.addView(dot, new LinearLayout.LayoutParams(dp(24), dp(24)));
        TextView l = text(label, 15, false, TEXT); l.setPadding(dp(12), 0, dp(8), 0);
        r.addView(l, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        r.addView(text(value, 13, false, ok ? MUTED : WARN));
        checklist.addView(r);
    }

    // =================================================================================================
    // RelayServer.Ui
    // =================================================================================================
    /** Controls the owner authorized on the PC; each press sends one request, the PC verifies and reports back. */
    @Override public void controls(org.json.JSONArray c) {
        runOnUiThread(() -> {
            int before = controlsBox.getChildCount();
            controlsBox.removeAllViews();
            int actions = 0;
            for (int i = 0; i < c.length(); i++) {
                org.json.JSONObject o = c.optJSONObject(i); if (o == null) continue;
                String id = o.optString("control_id"), label = o.optString("label"), kind = o.optString("kind", "button");
                if ("label".equals(kind)) {                         // layout v2: information only, never an action
                    TextView t = text(label, 13, true, MUTED); t.setPadding(dp(2), dp(4), 0, dp(2));
                    controlsBox.addView(t); controlsBox.addView(spacer(4)); continue;
                }
                if ("status".equals(kind)) {                        // last outcome of another control, pushed by the PC
                    String v = o.optString("value", "");
                    TextView t = text(label + "  ·  " + (v.isEmpty() ? "no result yet" : v), 13, false, v.startsWith("done") ? OK : v.isEmpty() ? FAINT : WARN);
                    t.setPadding(dp(2), dp(2), 0, dp(2)); t.setFocusable(true);
                    controlsBox.addView(t); controlsBox.addView(spacer(6)); continue;
                }
                actions++;
                final boolean confirm = "confirm".equals(kind);
                Button b = button(label, false);
                b.setTag(new String[]{id, label});
                // Hold to send: a tap does nothing, so stray or phantom touches (watch off the wrist) never send a command.
                final org.json.JSONObject[] down = new org.json.JSONObject[1];
                b.setOnTouchListener((v, e) -> {
                    if (e.getActionMasked() == android.view.MotionEvent.ACTION_DOWN) {
                        try { down[0] = new org.json.JSONObject().put("tool", e.getToolType(0)).put("pressure", Math.round(e.getPressure() * 100) / 100.0)
                                .put("size", Math.round(e.getSize() * 100) / 100.0).put("down_ms", 0).put("t", e.getEventTime()); } catch (Exception ignored) { }
                        orb.bump(0.3f);
                    }
                    return false;                                   // keep the normal click / long-click handling
                });
                b.setOnClickListener(v -> resultText.setText(confirm ? "Hold, then confirm" : "Hold the button to send"));
                b.setOnLongClickListener(v -> {
                    org.json.JSONObject touch = down[0];
                    try { if (touch != null) { touch.put("down_ms", android.os.SystemClock.uptimeMillis() - touch.getLong("t")); touch.remove("t"); } } catch (Exception ignored) { }
                    down[0] = null;
                    if (confirm) {                                  // the PC refuses a confirm control without this step
                        new android.app.AlertDialog.Builder(this)
                                .setTitle("Confirm")
                                .setMessage("Run \"" + label + "\" now?")
                                .setNegativeButton("Cancel", (d, w) -> resultText.setText("Cancelled"))
                                .setPositiveButton("Run", (d, w) -> sendPress(id, label, "confirm", touch))
                                .show();
                        return true;
                    }
                    sendPress(id, label, touch == null ? "key" : "long_press", touch);
                    return true;
                });
                controlsBox.addView(b); controlsBox.addView(spacer(8));
            }
            controlsCard.setVisibility(c.length() > 0 ? View.VISIBLE : View.GONE);
            if (before != controlsBox.getChildCount() && actions > 0) { log(actions + " control(s) authorized by your PC"); orb.pulse(); }
            relay.markRendered(relay.layoutRevision());             // ACK: this revision is on screen
            renderBusy();
            refresh();
        });
    }

    private void sendPress(String id, String label, String gesture, org.json.JSONObject touch) {
        String s = relay.press(id, gesture, touch);
        if (s != null) {
            resultText.setText(s);
            if (s.startsWith("Sent")) { log("Pressed " + label); thinkingUntil = System.currentTimeMillis() + 20_000; orb.pulse(); updateOrb(); }
        }
        renderBusy();                                               // feedback on the button itself: "Sending…", disabled
    }

    @Override public void result(String text) {
        runOnUiThread(() -> {
            resultText.setText(text); renderBusy();
            thinkingUntil = 0; setCaption(text); log(text); orb.pulse(); updateOrb();
        });
    }

    @Override public void commandResult(String text) { commandResult(text, false); }

    /** Voice-originated reports are spoken on this device; typed ones stay silent. */
    @Override public void commandResult(String text, boolean voice) {
        runOnUiThread(() -> {
            commandResult.setText("");
            thinkingUntil = 0;
            setCaption(text); log("OpenBridge: " + text); orb.pulse();
            if (voice && tts != null && text != null && !text.isEmpty()) {
                try { speaking = true; tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "ob-voice"); }
                catch (Exception ignored) { speaking = false; }
            }
            updateOrb();
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

    @Override public void status(String text) {
        runOnUiThread(() -> {
            statusLine.setText(text);
            if (text.startsWith("Scanning")) scanning = true;
            else if (text.startsWith("Scan finished") || text.startsWith("Pairing removed")) scanning = false;
            relayFailed = text.startsWith("Relay could not start");
            if (text.startsWith("Paired with")) setCaption("Paired. Ask me anything — type, or tap the orb to talk.");
            if (text.startsWith("Pairing removed")) setCaption("Pairing removed. Open OpenBridge on your PC to pair again.");
            log(text); orb.pulse(); refresh();
        });
    }

    @Override public void code(String c) {
        runOnUiThread(() -> {
            codeShown = c != null;
            codeCard.setVisibility(c == null ? View.GONE : View.VISIBLE);
            code.setText(c == null ? "" : c.substring(0, 3) + " " + c.substring(3));
            code.setContentDescription(c == null ? null : "Pairing code " + c);
            if (c != null) {
                log("Pairing requested by a PC");
                setCaption("Enter the code shown below on your PC.");
                orb.pulse();
                if (scroll != null) scroll.post(() -> scroll.smoothScrollTo(0, tv ? 0 : Math.max(0, codeCard.getTop() - dp(120))));
            }
            refresh();
        });
    }

    // =================================================================================================
    // View helpers
    // =================================================================================================
    private TextView[] tile(LinearLayout rowParent, String label) {
        LinearLayout t = new LinearLayout(this); t.setOrientation(LinearLayout.VERTICAL);
        t.setPadding(dp(14), dp(12), dp(14), dp(12)); t.setBackground(round(Color.argb(12, 255, 255, 255), Color.argb(22, 255, 255, 255), 16));
        LinearLayout top = new LinearLayout(this); top.setGravity(Gravity.CENTER_VERTICAL);
        TextView dot = text("●", 9, false, MUTED); dot.setPadding(0, 0, dp(6), 0);
        TextView l = text(label, 10, true, FAINT); l.setLetterSpacing(0.2f);
        top.addView(dot); top.addView(l); t.addView(top);
        TextView v = text("—", tv ? 18 : 16, false, TEXT, "sans-serif-medium"); v.setPadding(0, dp(4), 0, 0); t.addView(v);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        if (rowParent.getChildCount() > 0) lp.leftMargin = dp(8);
        rowParent.addView(t, lp);
        return new TextView[]{v, dot};
    }
    private void setTile(TextView value, TextView dot, String s, int color) { value.setText(s); dot.setTextColor(color); }

    private LinearLayout sectionTitle(String title, String hint) {
        LinearLayout r = new LinearLayout(this); r.setGravity(Gravity.CENTER_VERTICAL); r.setPadding(0, 0, 0, dp(10));
        TextView t = text(title, 11, true, MUTED); t.setLetterSpacing(0.2f);
        r.addView(t, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        if (hint != null) r.addView(text(hint, 11, false, FAINT));
        return r;
    }

    private LinearLayout card() {
        LinearLayout c = new LinearLayout(this); c.setOrientation(LinearLayout.VERTICAL); c.setPadding(dp(18), dp(16), dp(18), dp(16));
        c.setBackground(round(GLASS, GLASS_LINE, 22)); return c;
    }

    private Button button(String s, boolean primary) {
        Button b = new Button(this); b.setText(s); b.setAllCaps(false); b.setTextSize(tv ? 18 : 15);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        b.setTextColor(primary ? INK : TEXT); b.setMinHeight(dp(tv ? 60 : 52)); b.setFocusable(true); b.setStateListAnimator(null);
        b.setPadding(dp(18), 0, dp(18), 0);
        StateListDrawable states = new StateListDrawable();
        GradientDrawable focused = primary ? gradient(CYAN, VIOLET, 26) : round(Color.argb(46, 255, 255, 255), Color.WHITE, 26);
        focused.setStroke(dp(3), Color.WHITE);
        states.addState(new int[]{android.R.attr.state_focused}, focused);
        states.addState(new int[]{android.R.attr.state_pressed}, primary ? gradient(GlyphButton.lighten(CYAN, 0.3f), VIOLET, 26) : round(Color.argb(50, 0, 229, 255), CYAN, 26));
        states.addState(new int[]{-android.R.attr.state_enabled}, round(Color.argb(10, 255, 255, 255), GLASS_LINE, 26));
        states.addState(new int[]{}, primary ? gradient(CYAN, VIOLET, 26) : round(Color.argb(16, 255, 255, 255), GLASS_LINE, 26));
        b.setBackground(states); return b;
    }

    private StateListDrawable focusOnly(int radius) {
        StateListDrawable s = new StateListDrawable();
        GradientDrawable f = round(Color.argb(20, 255, 255, 255), Color.WHITE, radius); f.setStroke(dp(2), Color.WHITE);
        s.addState(new int[]{android.R.attr.state_focused}, f);
        s.addState(new int[]{}, round(Color.TRANSPARENT, Color.TRANSPARENT, radius));
        return s;
    }

    private GradientDrawable bg() {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{BG_TOP, Color.rgb(8, 8, 24), BG_BOTTOM});
        return d;
    }
    private GradientDrawable gradient(int a, int b, int radiusDp) {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{a, b});
        d.setCornerRadius(dp(radiusDp)); return d;
    }
    private GradientDrawable round(int fill, int stroke, int radiusDp) {
        GradientDrawable d = new GradientDrawable(); d.setColor(fill); d.setCornerRadius(dp(radiusDp)); d.setStroke(dp(1), stroke); return d;
    }
    private TextView text(String s, int size, boolean bold, int color) { return text(s, size, bold, color, null); }
    private TextView text(String s, int size, boolean bold, int color, String family) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(TypedValue.COMPLEX_UNIT_SP, size); t.setTextColor(color);
        t.setLineSpacing(0, 1.15f);
        if (family != null) t.setTypeface(Typeface.create(family, bold ? Typeface.BOLD : Typeface.NORMAL));
        else if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }
    private View spacer(int h) { View v = new View(this); v.setLayoutParams(new LinearLayout.LayoutParams(1, dp(h))); return v; }
    private int dp(int v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics())); }
}
