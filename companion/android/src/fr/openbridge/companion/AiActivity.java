package fr.openbridge.companion;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** AI on this phone: whether the engine and the models are here, when the phone answers by itself, message
 *  summaries for the glasses, the "OK Bridge" wake word, and a test box. */
public class AiActivity extends Activity {
    private final ExecutorService pool = Executors.newSingleThreadExecutor();
    private TextView state, answer;
    private EditText q;
    private Button modeBtn;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        LinearLayout col = Look.page(this, L.t("AI on this phone"), L.t("A small model and speech-to-text running on the phone, without the PC or the internet."));

        LinearLayout c1 = Look.card(this);
        c1.addView(Look.section(this, L.t("Engine and models")));
        state = Look.text(this, "", 13, false, Look.TEXT);
        state.setTypeface(android.graphics.Typeface.MONOSPACE);
        c1.addView(state);
        Look.add(c1, Look.text(this, L.t("Models are copied from the PC: openbridge companion ai push (USB debugging on)."), 12, false, Look.FAINT), 8);
        Look.add(col, c1, 0);

        LinearLayout c2 = Look.card(this);
        c2.addView(Look.section(this, L.t("When the phone answers")));
        modeBtn = Look.button(this, modeLabel(), Look.VIOLET, false);
        modeBtn.setOnClickListener(v -> {
            String m = LocalAi.mode(this);
            LocalAi.setMode(this, "auto".equals(m) ? "phone" : "phone".equals(m) ? "pc" : "auto");
            modeBtn.setText(modeLabel());
        });
        c2.addView(modeBtn);
        android.content.SharedPreferences ai = getSharedPreferences("ai", MODE_PRIVATE);
        Button sum = Look.add(c2, Look.toggle(this, L.t("Summarise long messages for the glasses"), ai.getBoolean("summaries", false)), 8);
        sum.setOnClickListener(v -> { boolean on = !(Boolean) v.getTag(); ai.edit().putBoolean("summaries", on).apply(); Look.setToggle(sum, L.t("Summarise long messages for the glasses"), on); });
        Button wake = Look.add(c2, Look.toggle(this, L.t("Wake word \"OK Bridge\""), WakeService.running()), 8);
        wake.setOnClickListener(v -> {
            boolean on = !(Boolean) v.getTag();
            if (on) {
                if (checkSelfPermission("android.permission.RECORD_AUDIO") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{"android.permission.RECORD_AUDIO"}, 51); return;
                }
                if (!LocalAi.sttReady(this)) { answer.setText(L.t("The wake word needs the speech model on the phone.")); return; }
                WakeService.start(this);
            } else WakeService.stop(this);
            Look.setToggle(wake, L.t("Wake word \"OK Bridge\""), on);
        });
        Look.add(c2, Look.text(this, L.t("The wake word keeps the microphone on with a visible notification and uses more battery. Off by default."), 12, false, Look.FAINT), 6);
        Look.add(col, c2, 14);

        LinearLayout c3 = Look.card(this);
        c3.addView(Look.section(this, L.t("Try it")));
        q = new EditText(this);
        q.setHint(L.t("Ask the phone…"));
        q.setTextColor(Look.TEXT);
        q.setHintTextColor(Look.FAINT);
        c3.addView(q);
        Button ask = Look.add(c3, Look.button(this, L.t("Ask the phone"), Look.MAGENTA, true), 8);
        ask.setOnClickListener(v -> test());
        Button oracle = Look.add(c3, Look.button(this, L.t("Open the Oracle (voice)"), Look.CYAN, false), 8);
        oracle.setOnClickListener(v -> startActivity(new Intent(this, OracleVoiceActivity.class)));
        answer = Look.add(c3, Look.text(this, "", 15, false, Look.OK), 10);
        Look.add(col, c3, 14);
        refresh();
    }

    private String modeLabel() {
        switch (LocalAi.mode(this)) {
            case "phone": return L.t("Always on the phone");
            case "pc": return L.t("Always on the PC");
            default: return L.t("Auto: on the phone when the PC is away");
        }
    }

    private static String mb(long n) { return n <= 0 ? "—" : String.format(Locale.ROOT, "%.0f MB", n / 1048576.0); }

    private void refresh() {
        StringBuilder s = new StringBuilder();
        s.append(L.t("Engine")).append(": ").append(LocalAi.engine() ? LocalAi.info() : L.t("not in this build")).append('\n');
        s.append(L.t("Language model")).append(": ").append(mb(LocalAi.llmFile(this).length())).append('\n');
        s.append(L.t("Speech model")).append(": ").append(mb(LocalAi.sttFile(this).length())).append('\n');
        s.append(L.t("Command model")).append(": ").append(mb(LocalAi.intentFile(this).length())).append('\n');
        s.append(L.t("Threads")).append(": ").append(LocalAi.threads());
        if (LocalAi.lastLlmMs > 0) s.append('\n').append(L.t("Last answer")).append(": ").append(LocalAi.lastLlmMs).append(" ms");
        if (LocalAi.lastIntentMs > 0) s.append('\n').append(L.t("Last command")).append(": ").append(LocalAi.lastIntentMs).append(" ms");
        if (LocalAi.lastSttMs > 0) s.append('\n').append(L.t("Last dictation")).append(": ").append(LocalAi.lastSttMs).append(" ms");
        state.setText(s.toString());
    }

    private void test() {
        String text = q.getText().toString().trim();
        if (text.isEmpty()) return;
        if (!LocalAi.llmReady(this)) { answer.setText(L.t("No model on the phone yet.")); return; }
        answer.setText(L.t("Thinking…"));
        pool.submit(() -> {
            String a = LocalAi.intentReady(this) ? LocalAi.handle(this, text) : LocalAi.ask(this, text);
            runOnUiThread(() -> { answer.setText(a == null ? L.t("No answer.") : a); refresh(); });
        });
    }

    @Override protected void onDestroy() { pool.shutdownNow(); super.onDestroy(); }
}
