package fr.openbridge.companion;

import android.content.Context;

import java.io.File;

/** AI on the phone itself, no PC and no network: a small language model (llama.cpp) and speech-to-text
 *  (whisper.cpp), both built into the app as one native library (libobai.so) and running on the phone's CPU.
 *
 *  The model files are not in the APK: the owner copies them to the app's folder (Android/data/fr.openbridge.companion
 *  /files/models: llm.gguf and stt.bin), from the PC with `openbridge companion ai push`, or downloads them on the AI
 *  page. Everything stays on the phone. */
final class LocalAi {
    private static boolean loaded;
    private static String loadError = "";
    static {
        try { System.loadLibrary("obai"); loaded = true; }
        catch (Throwable t) { loadError = String.valueOf(t.getMessage()); }
    }

    static native long llmInit(String path, int nCtx, int threads);
    static native String llmChat(long h, String system, String user, int maxTokens);
    static native void llmFree(long h);
    static native long sttInit(String path);
    static native String sttRun(long h, float[] pcm, String lang, int threads);
    static native void sttFree(long h);
    static native String info();

    private static long llm, stt, intent;
    private static String llmPath = "", sttPath = "";
    static volatile long lastLlmMs, lastSttMs;
    static volatile int lastTokens;

    private LocalAi() { }

    static boolean engine() { return loaded; }

    /** auto | phone | pc. Auto: the phone answers when no PC has been in touch for a minute, or in standalone mode. */
    static String mode(Context c) { return c.getSharedPreferences("ai", Context.MODE_PRIVATE).getString("mode", "auto"); }
    static void setMode(Context c, String m) { c.getSharedPreferences("ai", Context.MODE_PRIVATE).edit().putString("mode", m).apply(); }
    static boolean useLocal(Context c) {
        if (!llmReady(c)) return false;
        String m = mode(c);
        if ("phone".equals(m)) return true;
        if ("pc".equals(m)) return false;
        boolean pcAway = !RelayServer.get(c, null).paired() || System.currentTimeMillis() - RelayServer.lastPcAt > 60_000;
        return pcAway || (StandaloneHub.enabled(c) && StandaloneHub.get(c).active());
    }
    static String engineError() { return loadError; }

    static File dir(Context c) { File d = new File(c.getExternalFilesDir(null), "models"); d.mkdirs(); return d; }
    static File llmFile(Context c) { return new File(dir(c), "llm.gguf"); }
    static File sttFile(Context c) { return new File(dir(c), "stt.bin"); }
    /** The phone's own command model (fine-tuned on the PC: dev/ai_training/make_phone_dataset.py). */
    static File intentFile(Context c) { return new File(dir(c), "intent.gguf"); }
    static boolean intentReady(Context c) { return loaded && intentFile(c).length() > 1_000_000; }
    static boolean llmReady(Context c) { return loaded && llmFile(c).length() > 1_000_000; }
    static boolean sttReady(Context c) { return loaded && sttFile(c).length() > 1_000_000; }

    static int threads() { return Math.max(2, Math.min(6, Runtime.getRuntime().availableProcessors() - 2)); }

    static synchronized boolean loadLlm(Context c) {
        if (!llmReady(c)) return false;
        String p = llmFile(c).getPath();
        if (llm != 0 && p.equals(llmPath)) return true;
        if (llm != 0) { llmFree(llm); llm = 0; }
        long t0 = System.currentTimeMillis();
        llm = llmInit(p, 1024, threads());
        llmPath = p;
        Diag.log("local LLM loaded in " + (System.currentTimeMillis() - t0) + " ms" + (llm == 0 ? " (FAILED)" : ""));
        return llm != 0;
    }

    /** Same system line as the training data (D:/OpenBridgeAI/data_phone/system.txt). */
    static final String INTENT_SYSTEM = "Tu es le routeur de commandes du telephone OpenBridge. Reponds uniquement en JSON compact.";

    /** What the owner asked, as one of the phone's own orders ({"a": "nav" | "module" | ...}) or {"a": "ask"};
     *  null when the command model is not installed or did not answer with JSON. */
    static synchronized org.json.JSONObject intent(Context c, String text) {
        if (!intentReady(c)) return null;
        if (intent == 0) {
            long t0 = System.currentTimeMillis();
            intent = llmInit(intentFile(c).getPath(), 512, threads());
            Diag.log("command model loaded in " + (System.currentTimeMillis() - t0) + " ms" + (intent == 0 ? " (FAILED)" : ""));
            if (intent == 0) return null;
        }
        long t0 = System.currentTimeMillis();
        String plain = java.text.Normalizer.normalize(text.toLowerCase(), java.text.Normalizer.Form.NFKD).replaceAll("\\p{M}", "")
                .replaceAll("[^a-z0-9 ]", " ").replaceAll("\\s+", " ").trim();
        String out = llmChat(intent, INTENT_SYSTEM, plain, 40);
        lastIntentMs = System.currentTimeMillis() - t0;
        if (out == null) return null;
        out = clean(out);
        int a = out.indexOf('{'), b = out.lastIndexOf('}');
        if (a < 0 || b <= a) return null;
        try { return new org.json.JSONObject(out.substring(a, b + 1)); } catch (Exception e) { return null; }
    }
    static volatile long lastIntentMs;

    /** One utterance, end to end on the phone: the phone's own order if it is one, otherwise an answer. */
    static String handle(Context c, String text) {
        org.json.JSONObject o = intent(c, text);
        String done = PhoneActions.run(c, o, text);
        if (done != null) { Diag.log("phone order: " + o + " (" + lastIntentMs + " ms)"); return done; }
        return ask(c, text);
    }

    static synchronized void unload() {
        if (intent != 0) { llmFree(intent); intent = 0; }
        if (llm != 0) { llmFree(llm); llm = 0; llmPath = ""; }
        if (stt != 0) { sttFree(stt); stt = 0; sttPath = ""; }
    }

    static final String SYSTEM_FR = "Tu es l'Oracle d'OpenBridge, affiché dans des lunettes. Réponds en français, en une ou deux phrases courtes, sans mise en forme.";
    static final String SYSTEM_EN = "You are the OpenBridge Oracle, shown in smart glasses. Answer in one or two short sentences, plain text, no formatting.";

    /** One short answer for the glasses. Returns null when no model is installed. */
    static synchronized String ask(Context c, String question) {
        if (!loadLlm(c)) return null;
        long t0 = System.currentTimeMillis();
        String a = llmChat(llm, "fr".equals(L.lang) ? SYSTEM_FR : SYSTEM_EN, question, 96);
        lastLlmMs = System.currentTimeMillis() - t0;
        Diag.log("local LLM answered in " + lastLlmMs + " ms");
        return a == null ? null : clean(a);
    }

    /** Drops any reasoning block a model might still print, and the spaces around the answer. */
    static String clean(String a) {
        String s = a.replaceAll("(?s)<think>.*?</think>", "").replaceAll("(?s)^.*</think>", "");
        return s.replace("<|im_end|>", "").trim();
    }

    /** Two short lines for the glasses from a long message. */
    static synchronized String summarise(Context c, String text) {
        if (!loadLlm(c)) return null;
        String sys = "fr".equals(L.lang) ? "Résume ce message en 12 mots maximum, en français, sans guillemets." : "Summarise this message in at most 12 words, no quotes.";
        String r = llmChat(llm, sys, text, 32);
        return r == null ? null : clean(r);
    }

    /** Speech to text for 16 kHz mono PCM16. Returns null when no model is installed. */
    static synchronized String transcribe(Context c, byte[] pcm16, String lang) {
        if (!sttReady(c)) return null;
        String p = sttFile(c).getPath();
        if (stt == 0 || !p.equals(sttPath)) {
            if (stt != 0) sttFree(stt);
            long t0 = System.currentTimeMillis();
            stt = sttInit(p); sttPath = p;
            Diag.log("local speech model loaded in " + (System.currentTimeMillis() - t0) + " ms" + (stt == 0 ? " (FAILED)" : ""));
            if (stt == 0) return null;
        }
        float[] f = new float[pcm16.length / 2];
        for (int i = 0; i < f.length; i++) f[i] = (short) ((pcm16[2 * i] & 0xff) | (pcm16[2 * i + 1] << 8)) / 32768f;
        long t0 = System.currentTimeMillis();
        String s = sttRun(stt, f, lang, threads());
        lastSttMs = System.currentTimeMillis() - t0;
        return s == null ? null : s.trim();
    }
}
