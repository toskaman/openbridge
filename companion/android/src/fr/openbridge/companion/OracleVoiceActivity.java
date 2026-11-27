package fr.openbridge.companion;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * OpenBridge Voice AI Oracle — Android / Wear OS continuous voice listener.
 *
 * Uses Android's on-device SpeechRecognizer for ultra-fast speech detection and
 * dispatches transcripts to the PC Brain -> ENGO 3 MicroOLED HUD:
 *   1. Direct HTTP POST /api/v2/voice/oracle when oracle_host is passed (e.g. adb reverse
 *      127.0.0.1:51515), supporting speculative partial web pre-fetch & live HUD preview.
 *   2. Paired RelayServer.submitOracle(...) over the encrypted OpenBridge channel with
 *      instant long-poll wakeup (< 15 ms), zero IP configuration needed.
 */
public class OracleVoiceActivity extends Activity {

    private static final int    PORT_DEFAULT  = 51515;
    private static final String LANG_DEFAULT  = "fr-FR";
    private static final long   RESTART_FAST  = 110;
    private static final long   RESTART_BUSY  = 320;

    private SpeechRecognizer  mRecognizer;
    private Intent            mRecogIntent;
    private final Handler     mHandler   = new Handler(Looper.getMainLooper());
    private final ExecutorService mPool  = Executors.newSingleThreadExecutor();

    private String  mHost;
    private int     mPort;
    private String  mLang;
    private boolean mPaused    = false;
    private String  mLastSent  = "";
    private long    mLastSentAt = 0;

    private TextView statusBadge, heardView, answerView, hintView;
    private Button   langBtn;

    private final RelayServer.OracleListener mOracleListener = text -> runOnUiThread(() -> {
        if (answerView != null && text != null && !text.isEmpty()) {
            answerView.setText(text);
            statusBadge.setText("●  " + L.t("Listening… speak naturally"));
            statusBadge.setTextColor(Color.rgb(105, 240, 174));
        }
    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        L.init(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(Color.rgb(6, 8, 18));
        getWindow().setNavigationBarColor(Color.rgb(6, 8, 18));

        mHost = getIntent().getStringExtra("oracle_host");
        mPort = getIntent().getIntExtra("oracle_port", PORT_DEFAULT);
        mLang = getIntent().getStringExtra("oracle_lang");
        if (mLang == null || mLang.isEmpty()) {
            mLang = "fr".equals(L.resolved(this)) ? "fr-FR" : LANG_DEFAULT;
        }

        if (!RelayServer.get(this, null).moduleOracle()) {      // module switched off by the owner
            Toast.makeText(this, L.t("The Oracle is turned off for this device."), Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        buildUi();
        RelayServer.get(this, null).setOracleListener(mOracleListener);

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1);
        } else {
            startListening();
        }
    }

    private void buildUi() {
        boolean watch = getPackageManager().hasSystemFeature("android.hardware.type.watch");
        int pad = dp(watch ? 18 : 22);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, dp(24), pad, dp(24));
        GradientDrawable bg = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Color.rgb(6, 8, 18), Color.rgb(12, 16, 36)});
        root.setBackground(bg);

        TextView title = label("ORACLE ENGO 3", 18, true, Color.rgb(236, 240, 255));
        statusBadge = label("●  " + L.t("Listening… speak naturally"), 13, true, Color.rgb(105, 240, 174));
        statusBadge.setPadding(0, dp(6), 0, dp(16));

        LinearLayout cardQ = glassCard();
        cardQ.addView(label(L.t("Last question"), 11, true, Color.rgb(138, 148, 182)));
        heardView = label("—", 16, false, Color.rgb(0, 229, 255));
        heardView.setPadding(0, dp(6), 0, 0);
        cardQ.addView(heardView);

        LinearLayout cardA = glassCard();
        cardA.addView(label(L.t("ENGO 3 answer"), 11, true, Color.rgb(138, 148, 182)));
        answerView = label("—", 18, true, Color.rgb(105, 240, 174));
        answerView.setPadding(0, dp(6), 0, 0);
        cardA.addView(answerView);

        RelayServer r = RelayServer.get(this, null);
        String routeInfo = (mHost != null && !mHost.isEmpty())
                ? "Direct HTTP " + mHost + ":" + mPort
                : (r.paired() ? L.t("Live mic -> ENGO 3") : "Not paired — pair PC first");
        hintView = label(routeInfo, 12, false, Color.rgb(138, 148, 182));
        hintView.setPadding(0, dp(12), 0, dp(16));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER);

        langBtn = pillBtn(mLang.startsWith("fr") ? "FR" : "EN", Color.rgb(0, 229, 255), Color.rgb(6, 8, 18));
        langBtn.setOnClickListener(v -> {
            mLang = mLang.startsWith("fr") ? "en-US" : "fr-FR";
            langBtn.setText(mLang.startsWith("fr") ? "FR" : "EN");
            restartNow();
        });

        Button stopBtn = pillBtn(L.t("Stop Oracle"), Color.rgb(255, 82, 82), Color.WHITE);
        stopBtn.setOnClickListener(v -> finish());

        LinearLayout.LayoutParams lp1 = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        lp1.rightMargin = dp(8);
        LinearLayout.LayoutParams lp2 = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 2);
        actions.addView(langBtn, lp1);
        actions.addView(stopBtn, lp2);

        root.addView(title);
        root.addView(statusBadge);
        root.addView(cardQ);
        root.addView(spacer(12));
        root.addView(cardA);
        root.addView(hintView);
        root.addView(actions);
        setContentView(root);
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] grants) {
        if (req == 1 && grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            startListening();
        } else {
            Toast.makeText(this, L.t("Microphone unavailable."), Toast.LENGTH_LONG).show();
            finish();
        }
    }

    @Override
    protected void onDestroy() {
        mPaused = true;
        stopPcTranscription();
        mHandler.removeCallbacksAndMessages(null);
        RelayServer.get(this, null).setOracleListener(null);
        if (mRecognizer != null) {
            try { mRecognizer.destroy(); } catch (Exception ignored) {}
        }
        mPool.shutdownNow();
        super.onDestroy();
    }

    private void startListening() {
        if (mPaused) return;
        try {
            if (!SpeechRecognizer.isRecognitionAvailable(this) || (LocalAi.useLocal(this) && LocalAi.sttReady(this))) {
                startPcTranscription();          // record here; transcribe on the PC, or on the phone when it answers itself
                return;
            }
            mRecognizer = SpeechRecognizer.createSpeechRecognizer(this);
            mRecognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) {
                    statusBadge.setText("●  " + L.t("Listening… speak naturally"));
                    statusBadge.setTextColor(Color.rgb(105, 240, 174));
                }
                @Override public void onBeginningOfSpeech() {
                    statusBadge.setText("●  " + L.t("LISTENING"));
                    statusBadge.setTextColor(Color.rgb(0, 229, 255));
                }
                @Override public void onRmsChanged(float rms) {}
                @Override public void onBufferReceived(byte[] buf) {}
                @Override public void onEndOfSpeech() {
                    statusBadge.setText("●  " + L.t("THINKING"));
                    statusBadge.setTextColor(Color.rgb(255, 183, 77));
                }
                @Override
                public void onResults(Bundle results) {
                    ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (matches != null && !matches.isEmpty()) {
                        String transcript = matches.get(0).trim();
                        if (!transcript.isEmpty()) {
                            long now = System.currentTimeMillis();
                            if (!transcript.equalsIgnoreCase(mLastSent) || (now - mLastSentAt) > 2500) {
                                mLastSent = transcript;
                                mLastSentAt = now;
                                heardView.setText("> " + transcript);
                                dispatchOracle(transcript, false);
                            }
                        }
                    }
                    scheduleRestart(RESTART_FAST);
                }
                @Override
                public void onPartialResults(Bundle partial) {
                    ArrayList<String> unstable = partial.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (unstable != null && !unstable.isEmpty()) {
                        String p = unstable.get(0).trim();
                        if (!p.isEmpty()) {
                            heardView.setText("> " + p + " …");
                            if (mHost != null && !mHost.isEmpty()) {
                                dispatchOracle(p, true);
                            }
                        }
                    }
                }
                @Override
                public void onError(int error) {
                    long delay = (error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY) ? RESTART_BUSY : RESTART_FAST;
                    scheduleRestart(delay);
                }
                @Override public void onEvent(int type, Bundle extras) {}
            });

            mRecogIntent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, mLang);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 750L);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 600L);
            mRecogIntent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 220L);
            mRecognizer.startListening(mRecogIntent);
        } catch (Exception e) {
            scheduleRestart(RESTART_BUSY);
        }
    }

    // ---- Fallback for phones without a speech service: record here, transcribe on the PC (local model). ----
    private volatile boolean mPcLoop;
    private Thread mPcThread;

    private void startPcTranscription() {
        if (mPcLoop) return;
        RelayServer relay = RelayServer.get(this, null);
        if (!relay.paired() && !(LocalAi.useLocal(this) && LocalAi.sttReady(this))) {
            statusBadge.setText("●  " + L.t("Not paired — pair PC first"));
            statusBadge.setTextColor(Color.rgb(255, 82, 82));
            return;
        }
        mPcLoop = true;
        statusBadge.setText("●  " + L.t("Listening… speak naturally") + (LocalAi.useLocal(this) ? " (" + L.t("phone") + ")" : " (PC)"));
        statusBadge.setTextColor(Color.rgb(105, 240, 174));
        mPcThread = new Thread(this::pcLoop, "oracle-pc-mic");
        mPcThread.start();
    }

    private void stopPcTranscription() { mPcLoop = false; }

    /** Energy voice detection on 30 ms frames: an utterance starts after 2 loud frames (with 120 ms of pre-roll) and
     *  ends after 700 ms of silence or 8 s; shorter than 0.6 s is ignored. Each utterance goes to the paired PC as a
     *  voice clip marked "oracle"; the sound never leaves for anywhere else. */
    @android.annotation.SuppressLint("MissingPermission")
    private void pcLoop() {
        final int rate = 16000, frame = 480;
        android.media.AudioRecord rec = null;
        try {
            int min = android.media.AudioRecord.getMinBufferSize(rate, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT);
            rec = new android.media.AudioRecord(android.media.MediaRecorder.AudioSource.VOICE_RECOGNITION, rate,
                    android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT, Math.max(min, frame * 8));
            if (rec.getState() != android.media.AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("mic");
            rec.startRecording();
            short[] buf = new short[frame];
            java.util.ArrayDeque<byte[]> pre = new java.util.ArrayDeque<>();
            java.io.ByteArrayOutputStream utt = null;
            int loud = 0, quiet = 0, frames = 0;
            while (mPcLoop) {
                int n = rec.read(buf, 0, frame);
                if (n <= 0) continue;
                double sum = 0;
                byte[] b = new byte[n * 2];
                for (int i = 0; i < n; i++) { sum += (double) buf[i] * buf[i]; b[2 * i] = (byte) buf[i]; b[2 * i + 1] = (byte) (buf[i] >> 8); }
                double db = 20 * Math.log10(Math.max(1e-9, Math.sqrt(sum / n) / 32768.0));
                boolean active = db > -42;
                if (utt == null) {
                    pre.add(b); if (pre.size() > 4) pre.poll();
                    loud = active ? loud + 1 : 0;
                    if (loud >= 2) {
                        utt = new java.io.ByteArrayOutputStream();
                        for (byte[] p : pre) utt.write(p);
                        pre.clear(); quiet = 0; frames = 0;
                        runOnUiThread(() -> { statusBadge.setText("●  " + L.t("LISTENING")); statusBadge.setTextColor(Color.rgb(0, 229, 255)); });
                    }
                    continue;
                }
                utt.write(b); frames++;
                quiet = active ? 0 : quiet + 1;
                if (quiet >= 23 || frames >= 266) {
                    byte[] clip = utt.toByteArray(); utt = null; loud = 0;
                    if (clip.length >= 19200 && LocalAi.useLocal(this) && LocalAi.sttReady(this)) {
                        answerLocally(clip);
                    } else if (clip.length >= 19200) {                 // at least 0.6 s
                        String s = RelayServer.get(this, null).submitVoice(clip, "oracle");
                        runOnUiThread(() -> { statusBadge.setText("●  " + L.t("THINKING") + " · " + s); statusBadge.setTextColor(Color.rgb(255, 183, 77)); });
                    } else {
                        runOnUiThread(() -> { statusBadge.setText("●  " + L.t("Listening… speak naturally") + " (PC)"); statusBadge.setTextColor(Color.rgb(105, 240, 174)); });
                    }
                }
            }
        } catch (Exception e) {
            runOnUiThread(() -> { statusBadge.setText("●  " + L.t("Microphone unavailable.")); statusBadge.setTextColor(Color.rgb(255, 82, 82)); });
        } finally {
            if (rec != null) { try { rec.stop(); } catch (Exception ignored) { } rec.release(); }
            mPcLoop = false;
        }
    }

    private void restartNow() {
        mHandler.removeCallbacksAndMessages(null);
        if (mRecognizer != null) {
            try { mRecognizer.destroy(); } catch (Exception ignored) {}
            mRecognizer = null;
        }
        startListening();
    }

    private void scheduleRestart(long delayMs) {
        if (mPaused) return;
        mHandler.postDelayed(() -> {
            if (mPaused) return;
            if (mRecognizer != null) {
                try { mRecognizer.destroy(); } catch (Exception ignored) {}
                mRecognizer = null;
            }
            startListening();
        }, delayMs);
    }

    /** The phone answers by itself (PC away, or the owner chose "on the phone"): local speech-to-text, then the local
     *  model; the answer goes to this screen and, in standalone mode, to the glasses. */
    private void answerLocally(byte[] clip) {
        runOnUiThread(() -> { statusBadge.setText("●  " + L.t("THINKING") + " (" + L.t("phone") + ")"); statusBadge.setTextColor(Color.rgb(255, 183, 77)); });
        mPool.submit(() -> {
            String heard = LocalAi.transcribe(this, clip, mLang.startsWith("fr") ? "fr" : "en");
            if (heard == null || heard.isEmpty()) { runOnUiThread(() -> statusBadge.setText("●  " + L.t("I didn't catch that."))); return; }
            runOnUiThread(() -> heardView.setText(heard));
            answerText(heard);
        });
    }

    private void answerText(String q) {
        long t0 = System.currentTimeMillis();
        String a = LocalAi.intentReady(this) ? LocalAi.handle(this, q) : LocalAi.ask(this, q);
        if (a == null) { runOnUiThread(() -> answerView.setText(L.t("No model on the phone yet."))); return; }
        long ms = System.currentTimeMillis() - t0;
        if (StandaloneHub.enabled(this)) StandaloneHub.get(this).oracle(q, a);
        runOnUiThread(() -> {
            answerView.setText(a + " (" + ms + "ms, " + L.t("phone") + ")");
            statusBadge.setText("●  " + L.t("Listening… speak naturally") + " (" + L.t("phone") + ")");
            statusBadge.setTextColor(Color.rgb(105, 240, 174));
        });
    }

    private void dispatchOracle(String transcript, boolean isPartial) {
        if (!isPartial && LocalAi.useLocal(this) && LocalAi.llmReady(this)) {
            runOnUiThread(() -> heardView.setText(transcript));
            mPool.submit(() -> answerText(transcript));
            return;
        }
        if (!isPartial && (mHost == null || mHost.isEmpty())) {
            RelayServer relay = RelayServer.get(this, null);
            if (relay.paired()) {
                relay.submitOracle(transcript, "android_companion");
                return;
            }
        }
        if (mHost == null || mHost.isEmpty()) return;

        mPool.submit(() -> {
            try {
                String lang = mLang.startsWith("fr") ? "fr" : "en";
                JSONObject body = new JSONObject();
                body.put("transcript", transcript);
                body.put("language", lang);
                body.put("mic_source", "android_companion");
                if (isPartial) body.put("partial", true);

                byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
                URL url = new URL("http://" + mHost + ":" + mPort + "/api/v2/voice/oracle");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Content-Length", String.valueOf(data.length));
                conn.setConnectTimeout(isPartial ? 350 : 1000);
                conn.setReadTimeout(isPartial ? 800 : 5000);
                conn.setDoOutput(true);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(data);
                }
                int code = conn.getResponseCode();
                if (!isPartial && code == 200) {
                    try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                        StringBuilder sb = new StringBuilder();
                        String line;
                        while ((line = br.readLine()) != null) sb.append(line);
                        JSONObject resp = new JSONObject(sb.toString());
                        String ans = resp.optString("answer", "");
                        int lat = resp.optInt("latency_ms", 0);
                        if (!ans.isEmpty()) {
                            runOnUiThread(() -> answerView.setText(ans + " (" + lat + "ms)"));
                        }
                    }
                }
                conn.disconnect();
            } catch (Exception ignored) {}
        });
    }

    private TextView label(String s, int sp, boolean bold, int color) {
        TextView tv = new TextView(this);
        tv.setText(s);
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        tv.setTextColor(color);
        if (bold) tv.setTypeface(Typeface.DEFAULT_BOLD);
        return tv;
    }

    private LinearLayout glassCard() {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(16), dp(14), dp(16), dp(14));
        GradientDrawable d = new GradientDrawable();
        d.setColor(Color.argb(22, 255, 255, 255));
        d.setCornerRadius(dp(16));
        d.setStroke(dp(1), Color.argb(38, 255, 255, 255));
        c.setBackground(d);
        return c;
    }

    private Button pillBtn(String txt, int fill, int ink) {
        Button b = new Button(this);
        b.setText(txt);
        b.setTextColor(ink);
        b.setAllCaps(false);
        b.setTextSize(15);
        b.setMinHeight(dp(48));
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(24));
        b.setBackground(d);
        return b;
    }

    private View spacer(int h) {
        View v = new View(this);
        v.setLayoutParams(new LinearLayout.LayoutParams(1, dp(h)));
        return v;
    }

    private int dp(int v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()));
    }
}
