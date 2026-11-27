package fr.openbridge.companion;

import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.ToneGenerator;
import android.media.AudioManager;
import android.os.Build;
import android.os.IBinder;

import java.io.ByteArrayOutputStream;
import java.text.Normalizer;

/** "OK Bridge": hands-free commands. While the owner keeps it on (visible notification), the microphone is read on
 *  the phone only; short utterances are transcribed by the phone's own speech model and thrown away unless they start
 *  with the wake word. Then the command is handled: glasses navigation words on the phone, anything else sent to the
 *  paired PC as a typed command would be, or answered by the phone's model when the PC is away. */
public class WakeService extends Service {
    static final String CHANNEL = "wake_word";
    static final int NOTIF_ID = 44;
    private static volatile boolean running;
    private volatile boolean loop;
    private Thread thread;

    static boolean running() { return running; }
    static void start(Context c) { c.startForegroundService(new Intent(c, WakeService.class)); }
    static void stop(Context c) { c.stopService(new Intent(c, WakeService.class)); }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        L.init(this);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.createNotificationChannel(new NotificationChannel(CHANNEL, L.t("Wake word"), NotificationManager.IMPORTANCE_LOW));
        int small = getResources().getIdentifier("ic_oracle", "drawable", getPackageName());
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(small != 0 ? small : android.R.drawable.ic_btn_speak_now)
                .setContentTitle(L.t("Listening for \"OK Bridge\""))
                .setContentText(L.t("On the phone only. Tap to turn off."))
                .setContentIntent(PendingIntent.getActivity(this, 3, new Intent(this, AiActivity.class), PendingIntent.FLAG_IMMUTABLE))
                .setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 30) startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        else startForeground(NOTIF_ID, n);
        if (!loop) {
            loop = true;
            thread = new Thread(this::listen, "wake-word");
            thread.start();
        }
        running = true;
        Diag.log("wake word on");
        return START_STICKY;
    }

    static String plain(String s) {
        String n = Normalizer.normalize(s == null ? "" : s.toLowerCase(), Normalizer.Form.NFKD).replaceAll("\\p{M}", "");
        return n.replaceAll("[^a-z0-9' ]", " ").replaceAll("\\s+", " ").trim();
    }

    /** "ok bridge, ..." -> the rest ("" when only the wake word); null when there is no wake word. */
    static String afterWake(String heard) {
        String p = plain(heard);
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("^(?:ok|okay|o k|hey|eh)\\s*(?:open\\s*)?(?:bridge|bridj|brigde|brige|bridges|breach|bridget)\\b\\s*(.*)$").matcher(p);
        return m.find() ? m.group(1).trim() : null;
    }

    @SuppressLint("MissingPermission")
    private void listen() {
        final int rate = 16000, frame = 480;
        AudioRecord rec = null;
        String pending = null;          // wake word heard, waiting for the command
        long wokeAt = 0;
        try {
            int min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            rec = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(min, frame * 8));
            rec.startRecording();
            short[] buf = new short[frame];
            java.util.ArrayDeque<byte[]> pre = new java.util.ArrayDeque<>();
            ByteArrayOutputStream utt = null;
            int loud = 0, quiet = 0, frames = 0;
            while (loop) {
                int n = rec.read(buf, 0, frame);
                if (n <= 0) continue;
                double sum = 0;
                byte[] b = new byte[n * 2];
                for (int i = 0; i < n; i++) { sum += (double) buf[i] * buf[i]; b[2 * i] = (byte) buf[i]; b[2 * i + 1] = (byte) (buf[i] >> 8); }
                boolean active = 20 * Math.log10(Math.max(1e-9, Math.sqrt(sum / n) / 32768.0)) > -40;
                if (pending != null && System.currentTimeMillis() - wokeAt > 7000) pending = null;   // wake word, then silence
                if (utt == null) {
                    pre.add(b); if (pre.size() > 6) pre.poll();
                    loud = active ? loud + 1 : 0;
                    if (loud >= 2) { utt = new ByteArrayOutputStream(); for (byte[] p : pre) utt.write(p); pre.clear(); quiet = 0; frames = 0; }
                    continue;
                }
                utt.write(b); frames++;
                quiet = active ? 0 : quiet + 1;
                int maxFrames = pending != null ? 266 : 100;           // 8 s for a command, 3 s for the wake word
                if (quiet >= 20 || frames >= maxFrames) {
                    byte[] clip = utt.toByteArray(); utt = null; loud = 0;
                    if (clip.length < 12800) continue;                 // under 0.4 s
                    String heard = LocalAi.transcribe(this, clip, "fr".equals(L.lang) ? "fr" : "en");
                    if (heard == null) continue;
                    if (pending != null) { pending = null; handle(heard); continue; }
                    String rest = afterWake(heard);
                    if (rest == null) continue;
                    beep();
                    if (rest.isEmpty()) { pending = ""; wokeAt = System.currentTimeMillis(); }
                    else handle(rest);
                }
            }
        } catch (Exception e) {
            Diag.log("wake word: " + e.getMessage());
        } finally {
            if (rec != null) { try { rec.stop(); } catch (Exception ignored) { } rec.release(); }
        }
    }

    private void beep() {
        try { new ToneGenerator(AudioManager.STREAM_NOTIFICATION, 60).startTone(ToneGenerator.TONE_PROP_BEEP, 120); } catch (Exception ignored) { }
    }

    private void handle(String said) {
        String p = plain(said);
        Diag.log("wake word command: " + p);
        String nav = p.matches("(suivant|next|apres)") ? "next" : p.matches("(ouvre|ouvrir|open|ok|valide)") ? "ok"
                : p.matches("(retour|back|precedent)") ? "back" : p.matches("(accueil|home|menu)") ? "home" : null;
        RelayServer r = RelayServer.get(this, null);
        if (nav != null) { r.glasses().button(nav); return; }
        String done = PhoneActions.run(this, LocalAi.intent(this, said), said);     // the phone's own orders, PC or not
        if (done != null) { Diag.log("wake word: " + done); return; }
        if (LocalAi.useLocal(this)) {
            String a = LocalAi.ask(this, said);
            if (a != null && StandaloneHub.enabled(this)) StandaloneHub.get(this).oracle(said, a);
            return;
        }
        if (r.paired()) r.submitCommand(said);
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onDestroy() {
        loop = false;
        running = false;
        if (thread != null) thread.interrupt();
        Diag.log("wake word off");
        super.onDestroy();
    }
}
