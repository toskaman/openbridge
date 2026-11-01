package fr.openbridge.companion;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.os.ParcelUuid;
import android.util.SparseArray;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONArray;
import org.json.JSONObject;

/** OpenBridge relay protocol v1, relay side. Closed operation set, HMAC-SHA256, nonce + expiry, bounded BLE scans. */
final class RelayServer {
    static final String PROTOCOL = "openbridge-relay/1";
    static final int PORT = 47800;
    static final int MAX_SCAN_SECONDS = 15;
    static final int MAX_OBSERVATIONS = 200;
    private static final int MAX_BODY = 16384;

    interface Ui { void status(String text); void code(String code); default void controls(JSONArray c) { } default void result(String text) { } default void nsd(boolean ok, int err) { } default void commandResult(String text) { } default void commandResult(String text, boolean voice) { commandResult(text); }
        /** Live data flow for the UI: out = this device -> PC. label = operation, bytes = payload size. */
        default void flow(boolean out, String label, int bytes) { } }
    static final int MAX_CONTROLS = 12, MAX_QUEUE = 16;
    static final int MAX_COMMANDS = 8, MAX_COMMAND_TEXT = 500;
    /** Owner-typed NL commands queued on this device; the PC drains them and reports parse outcomes. Never auto-executed. */
    private final java.util.ArrayDeque<JSONObject> commands = new java.util.ArrayDeque<>();
    private final java.util.Set<String> pendingCommands = new java.util.HashSet<>();
    /** Voice clips: raw PCM16 mono 16 kHz, at most 15 s (480 000 bytes), at most 3 held. Dropped when the PC reports. */
    static final int VOICE_MAX_BYTES = 480000, MAX_CLIPS = 3;
    private final Map<String, byte[]> clips = new LinkedHashMap<>();
    private final Map<String, String> clipRequest = new java.util.HashMap<>();   // clip_id -> request_id
    private final java.util.Set<String> voiceRequests = new java.util.HashSet<>();
    /** Owner-authorized controls pushed by the paired PC (label + id only; the PC keeps skill, target and params). */
    private JSONArray controls = new JSONArray();
    private final java.util.ArrayDeque<JSONObject> requests = new java.util.ArrayDeque<>();
    private long lastPress;
    /** Layout v2: revision the PC asked for, and the revision the screen actually rendered (reported back as the ACK). */
    private volatile long renderedRevision = -1;
    void markRendered(long revision) { renderedRevision = revision; }
    long layoutRevision() { return prefs.getLong("layout_revision", 0); }
    static boolean actionKind(String kind) { return "button".equals(kind) || "confirm".equals(kind); }
    static final long PENDING_TIMEOUT_MS = 20_000;
    /** request_id -> time the PC fetched it. Cleared by the PC's signed result; never re-sent (at-most-once). */
    private final java.util.Map<String, Long> pending = new java.util.HashMap<>();
    /** request_id -> control_id for requests fetched by the PC and not yet answered. */
    private final java.util.Map<String, String> pendingControls = new java.util.HashMap<>();
    boolean busy(String controlId) {
        synchronized (requests) {
            for (JSONObject q : requests) if (controlId.equals(q.optString("control_id"))) return true;
            return pendingControls.containsValue(controlId);
        }
    }

    /** Called by the UI timer: a fetched request without a result in time is shown as unconfirmed, never re-sent. */
    String expirePending() {
        long now = System.currentTimeMillis(); int n = 0;
        synchronized (requests) {
            java.util.Iterator<java.util.Map.Entry<String, Long>> it = pending.entrySet().iterator();
            while (it.hasNext()) { java.util.Map.Entry<String, Long> e = it.next(); if (now - e.getValue() > PENDING_TIMEOUT_MS) { pendingControls.remove(e.getKey()); it.remove(); n++; } }
        }
        return n == 0 ? null : "Not confirmed by your PC. Check the device before pressing again.";
    }

    private final Context ctx;
    private volatile Ui ui;
    private final SharedPreferences prefs;
    private final SecureRandom random = new SecureRandom();
    /** nonce -> expires_at (s). A nonce is forgotten only after its command expired; never evicted while live. */
    private final Map<String, Long> seen = new LinkedHashMap<>();
    private static final int MAX_NONCES = 512;
    /** nonce -> last reply. A retried request (lost response, transport failover) gets the original
        reply instead of re-executing: exactly-once execution with at-least-once delivery. Swept with
        `seen`; cleared on (re)pairing and unpair. Guarded by the `seen` monitor. */
    private final Map<String, JSONObject> replies = new LinkedHashMap<>();
    private volatile boolean running;
    private static RelayServer instance;
    volatile boolean foreground;

    /** One relay per process: survives the activity being destroyed while a settings screen is open (low-RAM TVs). */
    /** Headless sink so the relay keeps serving when no screen is attached (foreground service). */
    static final Ui NOOP = new Ui() {
        @Override public void status(String text) { }
        @Override public void code(String code) { }
    };
    static synchronized RelayServer get(Context ctx, Ui ui) {
        Ui sink = (ui != null) ? ui : NOOP;
        if (instance == null) instance = new RelayServer(ctx.getApplicationContext(), sink);
        else if (ui != null) instance.ui = ui;   // a live screen re-attach wins; a headless (service) lookup never detaches it
        if (ui != null) instance.replayPendingCode(ui);   // a re-attached screen missed earlier ui.code() calls
        return instance;
    }
    /** Live pairing code, if one is still valid; null once paired, expired or never requested. */
    private synchronized String livePendingCode() {
        if (pendingCode == null || System.currentTimeMillis() > pendingUntil) return null;
        return pendingCode;
    }
    /** Re-deliver the live code to a (re-)attached screen; a no-op when none is live. */
    private void replayPendingCode(Ui sink) {
        String live = livePendingCode();
        if (live != null) sink.code(live);
    }
    /** A screen going away drops its own sink so relay callbacks stop and it can be GC'd. */
    static synchronized void release(Ui ui) {
        if (instance != null && instance.ui == ui) instance.ui = NOOP;
    }
    private ServerSocket server;
    private NsdManager.RegistrationListener nsdListener;
    private android.net.wifi.WifiManager.MulticastLock multicastLock;
    private String pendingCode, pendingRelayNonce, pendingPcNonce;
    private long pendingUntil;
    private int failedPairing;
    private volatile boolean scanning;

    RelayServer(Context ctx, Ui ui) {
        this.ctx = ctx; this.ui = ui;
        this.prefs = ctx.getSharedPreferences("relay", Context.MODE_PRIVATE);
    }

    boolean paired() { return prefs.contains("key"); }
    boolean ownerEnabled() { return prefs.getBoolean("owner_enabled", false); }
    void setOwnerEnabled(boolean v) { prefs.edit().putBoolean("owner_enabled", v).apply(); }
    /** Standing owner consent for PC-initiated invokes. Explicit on-device toggle only, default off. */
    boolean fullControl() { return paired() && prefs.getBoolean("full_control", false); }
    void setFullControl(boolean v) { prefs.edit().putBoolean("full_control", v).apply(); }
    String relayId() {
        String id = prefs.getString("relay_id", null);
        if (id == null) { id = "relay-" + hex(bytes(6)); prefs.edit().putString("relay_id", id).apply(); }
        return id;
    }
    JSONArray controls() {
        synchronized (requests) {
            if (controls.length() == 0) { try { controls = new JSONArray(prefs.getString("controls", "[]")); } catch (Exception e) { controls = new JSONArray(); } }
            return controls;
        }
    }

    /** The owner pressed a control on this device: queue one request; the PC picks it up over the signed channel. */
    String press(String controlId) { return press(controlId, "click", null); }

    /** gesture + coarse touch info travel with the request so the PC can tell a deliberate hold from a phantom touch. */
    String press(String controlId, String gesture, JSONObject touch) {
        if (!paired()) return "Not paired with a PC";
        long now = System.currentTimeMillis();
        synchronized (requests) {
            if (now - lastPress < 400) return null;                 // debounce one physical press
            boolean known = false;
            JSONArray cs = controls();
            for (int i = 0; i < cs.length(); i++) if (cs.optJSONObject(i) != null && controlId.equals(cs.optJSONObject(i).optString("control_id"))) known = true;
            if (!known) return "This control is no longer authorized";
            for (int i = 0; i < cs.length(); i++) {
                JSONObject c = cs.optJSONObject(i);
                if (c != null && controlId.equals(c.optString("control_id")) && !actionKind(c.optString("kind", "button"))) return "This item only shows information";
            }
            if (requests.size() >= MAX_QUEUE) return "Too many pending requests; wait for the PC";
            for (JSONObject q : requests) if (controlId.equals(q.optString("control_id"))) return "Already sending…";
            if (pendingControls.containsValue(controlId)) return "Already sending…";   // one press in flight per control
            lastPress = now;
            long seq = prefs.getLong("press_seq", 0) + 1; prefs.edit().putLong("press_seq", seq).apply();
            try {
                JSONObject r = new JSONObject().put("request_id", hex(bytes(16))).put("control_id", controlId).put("pressed_at", now)
                        .put("seq", seq).put("gesture", gesture);
                if (touch != null) r.put("touch", touch);
                requests.add(r);
                android.util.Log.i("OpenBridgeRemote", "request seq=" + seq + " control=" + controlId + " gesture=" + gesture + " touch=" + touch);
            }
            catch (Exception e) { return "Could not queue the request"; }
        }
        return "Sent to your PC…";
    }

    /** Queue one owner-typed command for the PC to parse (local tiers only). Explicit send; nothing automatic. */
    String submitCommand(String text) {
        if (!paired()) return "Not paired with a PC";
        String t = text == null ? "" : text.trim();
        if (t.isEmpty()) return "Type a command first";
        if (t.length() > MAX_COMMAND_TEXT) return "Command too long (500 characters max)";
        synchronized (commands) {
            if (commands.size() >= MAX_COMMANDS) return "Too many pending commands; wait for the PC";
            try {
                String lang = java.util.Locale.getDefault().getLanguage().startsWith("fr") ? "fr" : "en";
                commands.add(new JSONObject().put("request_id", hex(bytes(16))).put("text", t).put("lang", lang).put("quality", "auto"));
            } catch (Exception e) { return "Could not queue the command"; }
        }
        return "Sent to your PC…";
    }

    /** Queue one owner-recorded voice clip: the PC downloads the bytes, transcribes locally, parses as text. */
    String submitVoice(byte[] pcm) {
        if (!paired()) return "Not paired with a PC";
        if (pcm == null || pcm.length < 16000 || pcm.length > VOICE_MAX_BYTES || pcm.length % 2 != 0)
            return pcm != null && pcm.length < 16000 ? "Too short — hold a little longer" : "Voice clip too long (15 seconds max)";
        synchronized (commands) {
            if (commands.size() >= MAX_COMMANDS) return "Too many pending commands; wait for the PC";
            try {
                String lang = java.util.Locale.getDefault().getLanguage().startsWith("fr") ? "fr" : "en";
                String clip = "v" + hex(bytes(6));
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                String req = hex(bytes(16));
                commands.add(new JSONObject().put("request_id", req).put("kind", "voice").put("clip_id", clip)
                        .put("bytes", pcm.length).put("sha256", hex(sha.digest(pcm))).put("lang", lang).put("quality", "auto"));
                clips.put(clip, pcm); clipRequest.put(clip, req); voiceRequests.add(req);
                while (clips.size() > MAX_CLIPS) {  // evict oldest held clip and its queued announcement
                    String old = clips.keySet().iterator().next();
                    clips.remove(old); String rq = clipRequest.remove(old); voiceRequests.remove(rq);
                    commands.removeIf(o -> rq != null && rq.equals(o.optString("request_id")));
                }
            } catch (Exception e) { return "Could not queue the voice clip"; }
        }
        return "Sent voice to your PC…";
    }

    /** One-shot signed download of a queued voice clip. Mirrors the PC's voice_url HMAC byte for byte. */
    private void serveVoice(Socket c, String request) throws Exception {
        Map<String, String> q = new LinkedHashMap<>();
        String qs = request.substring("GET /voice?".length(), request.lastIndexOf(' '));
        for (String part : qs.split("&")) { int eq = part.indexOf('='); if (eq > 0) q.put(part.substring(0, eq), part.substring(eq + 1)); }
        byte[] key = key();
        String clip = q.get("clip"), ts = q.get("ts"), nonce = q.get("nonce"), sig = q.get("sig");
        long now = System.currentTimeMillis() / 1000, t = -1;
        try { t = Long.parseLong(ts == null ? "" : ts); } catch (NumberFormatException ignored) { }
        boolean ok = key != null && clip != null && clip.matches("[a-z0-9-]{1,32}")
                && t > 0 && Math.abs(now - t) <= 120 && nonce != null && nonce.matches("[0-9a-f]{16}") && sig != null;
        // Voice fetch is an idempotent read: the same signed URL may be retried (transport
        // failover) within its 120 s HMAC window. No one-shot marking; clips drop on report.
        if (ok) {
            try {
                if (!MessageDigest.isEqual(hex(hmac(key, "voice-v1|" + clip + "|" + t + "|" + nonce)).getBytes(), sig.getBytes())) ok = false;
            } catch (Exception e) { ok = false; }
        }
        byte[] pcm;
        synchronized (commands) { pcm = ok ? clips.get(clip) : null; }   // same lock as submitVoice/report
        if (!ok || pcm == null) { respond(c, ok ? 404 : 403, "{\"error\":\"" + (ok ? "gone" : "forbidden") + "\"}"); return; }
        String enc = "";
        if (prefs.getBoolean("require_aead", false)) {               // aead1 negotiated: the clip never leaves in clear
            pcm = Aead.sealVoice(key, Aead.VERSION + "|" + relayId() + "|voice|" + clip, pcm);
            enc = "X-OB-Enc: " + Aead.VERSION + "\r\n";
        }
        byte[] head = ("HTTP/1.0 200 X\r\nContent-Type: application/octet-stream\r\n" + enc + "Content-Length: " + pcm.length + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII);
        OutputStream out = c.getOutputStream();
        ui.flow(false, "voice fetch", request.length());
        out.write(head); out.write(pcm); out.flush();
        ui.flow(true, "voice clip", pcm.length);
    }

    void unpair() { synchronized (requests) { controls = new JSONArray(); requests.clear(); } synchronized (commands) { commands.clear(); pendingCommands.clear(); clips.clear(); clipRequest.clear(); voiceRequests.clear(); } synchronized (seen) { seen.clear(); replies.clear(); }
        prefs.edit().remove("controls").remove("key").remove("require_aead").putBoolean("owner_enabled", false).putBoolean("full_control", false).commit(); ui.status("Pairing removed. This device no longer accepts commands."); }

    boolean bleHardware() { return ctx.getPackageManager().hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE); }
    boolean scanPermission() {
        if (Build.VERSION.SDK_INT >= 31) return ctx.checkSelfPermission("android.permission.BLUETOOTH_SCAN") == PackageManager.PERMISSION_GRANTED;
        return ctx.checkSelfPermission("android.permission.ACCESS_FINE_LOCATION") == PackageManager.PERMISSION_GRANTED;
    }
    boolean locationOn() {
        if (Build.VERSION.SDK_INT >= 31) return true;   // not required with neverForLocation on Android 12+
        android.location.LocationManager lm = (android.location.LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
        try { return lm != null && (lm.isProviderEnabled(android.location.LocationManager.GPS_PROVIDER) || lm.isProviderEnabled(android.location.LocationManager.NETWORK_PROVIDER)); }
        catch (Exception e) { return false; }
    }
    /** False when the system Bluetooth app itself is disabled (seen on a debloated Android TV): nothing can turn the radio on. */
    boolean bluetoothServiceEnabled() {
        try {
            int st = ctx.getPackageManager().getApplicationEnabledSetting("com.android.bluetooth");
            return st != PackageManager.COMPONENT_ENABLED_STATE_DISABLED && st != PackageManager.COMPONENT_ENABLED_STATE_DISABLED_USER;
        } catch (Exception e) { return true; }   // package not visible: assume vendor stack
    }
    boolean bluetoothOn() {
        BluetoothManager m = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter a = m == null ? null : m.getAdapter();
        return a != null && a.isEnabled();
    }

    void start() {
        if (running) return;
        running = true;
        new Thread(() -> {
            try (ServerSocket s = new ServerSocket(PORT, 8, InetAddress.getByName("0.0.0.0"))) {
                server = s;
                try { new android.os.Handler(ctx.getMainLooper()).post(this::registerNsd); }
                catch (Exception ignored) { registerNsd(); }
                ui.status("Listening for OpenBridge on port " + PORT + (paired() ? " · paired" : " · not paired"));
                while (running) {
                    try (Socket c = s.accept()) { c.setSoTimeout(5000); handle(c); } catch (Exception ignored) { }
                }
            } catch (Exception e) { ui.status("Relay could not start: " + e.getClass().getSimpleName()); running = false; }
        }, "openbridge-relay").start();
    }

    void stop() { running = false;
        try { new android.os.Handler(ctx.getMainLooper()).post(this::unregisterNsd); }
        catch (Exception ignored) { unregisterNsd(); }
        try { if (server != null) server.close(); } catch (Exception ignored) { } }

    /** mDNS advertisement so the PC finds this relay on the LAN with no adb address and no setup.
     *  The broadcast carries the relay id (useless without the on-screen pairing code), the protocol,
     *  the app version, the form factor and the model. Registration needs no permission; it lives and
     *  dies with the relay socket. Failures are silent: pairing via a typed address still works. */
    static final String NSD_TYPE = "_openbridge-relay._tcp.";
    private void registerNsd() {
        try {
            NsdManager nsd = (NsdManager) ctx.getSystemService(Context.NSD_SERVICE);
            if (nsd == null) { ui.nsd(false, -2); return; }
            unregisterNsd();
            try {
                android.net.wifi.WifiManager wm = (android.net.wifi.WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
                multicastLock = wm.createMulticastLock("openbridge-nsd");
                multicastLock.setReferenceCounted(true);
                multicastLock.acquire();
            } catch (Exception ignored) { multicastLock = null; }
            String id = relayId();
            NsdServiceInfo info = new NsdServiceInfo();
            info.setServiceName("OpenBridge-" + id.substring(Math.max(0, id.length() - 12)));
            info.setServiceType(NSD_TYPE);
            info.setPort(PORT);
            info.setAttribute("relay", id);
            info.setAttribute("proto", PROTOCOL);
            try {
                info.setAttribute("ver", String.valueOf(ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0).versionCode));
            } catch (Exception ignored) { info.setAttribute("ver", "0"); }
            PackageManager pm = ctx.getPackageManager();
            info.setAttribute("form", pm.hasSystemFeature("android.hardware.type.watch") ? "watch"
                    : pm.hasSystemFeature(PackageManager.FEATURE_LEANBACK) ? "tv" : "phone");
            info.setAttribute("label", Build.MODEL == null ? "Android" : Build.MODEL);
            nsdListener = new NsdManager.RegistrationListener() {
                @Override public void onServiceRegistered(NsdServiceInfo s) { ui.nsd(true, 0); }
                @Override public void onRegistrationFailed(NsdServiceInfo s, int e) { nsdListener = null; ui.nsd(false, e); }
                @Override public void onServiceUnregistered(NsdServiceInfo s) { }
                @Override public void onUnregistrationFailed(NsdServiceInfo s, int e) { nsdListener = null; }
            };
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, nsdListener);
        } catch (Exception e) { nsdListener = null; ui.nsd(false, -1); }
    }
    private void unregisterNsd() {
        NsdManager.RegistrationListener l = nsdListener; nsdListener = null;
        if (l != null) {
            try {
                NsdManager nsd = (NsdManager) ctx.getSystemService(Context.NSD_SERVICE);
                if (nsd != null) nsd.unregisterService(l);
            } catch (Exception ignored) { }
        }
        if (multicastLock != null) {
            try { while (multicastLock.isHeld()) multicastLock.release(); } catch (Exception ignored) { }
            multicastLock = null;
        }
    }

    private void handle(Socket c) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
        String line; int length = -1;
        String request = in.readLine();
        if (request == null) { respond(c, 404, "{\"error\":\"not found\"}"); return; }
        if (request.startsWith("GET /voice?")) {
            while ((line = in.readLine()) != null && !line.isEmpty()) { }   // consume headers, no body
            try { serveVoice(c, request); } catch (Exception e) { respond(c, 403, "{\"error\":\"forbidden\"}"); }
            return;
        }
        if (!request.startsWith("POST /ob ")) { respond(c, 404, "{\"error\":\"not found\"}"); return; }
        while ((line = in.readLine()) != null && !line.isEmpty()) {
            if (line.toLowerCase().startsWith("content-length:")) length = Integer.parseInt(line.substring(15).trim());
        }
        if (length < 0 || length > MAX_BODY) { respond(c, 413, "{\"error\":\"size\"}"); return; }
        char[] buf = new char[length]; int read = 0;
        while (read < length) { int n = in.read(buf, read, length - read); if (n < 0) break; read += n; }
        JSONObject msg = new JSONObject(new String(buf, 0, read));
        // aead1: once the PC has sent one sealed message, plaintext commands are refused (no silent downgrade).
        boolean sealed = Aead.VERSION.equals(msg.optString("enc"));
        byte[] k = key();
        String rid = relayId();
        if (sealed) {
            if (k == null || !rid.equals(msg.optString("relay_id"))) { respond(c, 403, "{\"error\":\"not paired\"}"); return; }
            try { msg = new JSONObject(new String(Aead.open(k, Aead.aad(rid, "pc>relay"), msg), StandardCharsets.UTF_8)); }
            catch (Exception e) { respond(c, 403, "{\"error\":\"bad envelope\"}"); return; }
            if (!prefs.getBoolean("require_aead", false)) prefs.edit().putBoolean("require_aead", true).apply();
        }
        JSONObject reply;
        lastOp = msg.optString("op", sealed ? "sealed" : "request");
        try {
            reply = dispatch(msg, sealed);
            String rn = msg.optString("nonce");
            if (!rn.isEmpty()) {
                synchronized (seen) {
                    replies.put(rn, reply);
                    replies.keySet().retainAll(seen.keySet());
                }
            }
        }
        catch (SecurityException e) {
            if ("replay".equals(e.getMessage())) {
                JSONObject cached;
                synchronized (seen) { cached = replies.get(msg.optString("nonce")); }
                if (cached != null) {
                    String body = sealed ? Aead.seal(k, Aead.aad(rid, "relay>pc"), cached.toString().getBytes(StandardCharsets.UTF_8), null).toString()
                                             : cached.toString();
                    respond(c, 200, body);
                    ui.flow(false, lastOp, read);
                    ui.flow(true, "replay-cached", body.length());
                    return;
                }
            }
            ui.flow(false, lastOp, read);
            String err = new JSONObject().put("error", e.getMessage()).toString();
            respond(c, 403, err);
            ui.flow(true, "denied", err.length());
            return;
        }
        ui.flow(false, lastOp, read);
        String body = sealed ? Aead.seal(k, Aead.aad(rid, "relay>pc"), reply.toString().getBytes(StandardCharsets.UTF_8), null).toString()
                             : reply.toString();
        respond(c, 200, body);
        ui.flow(true, lastOp, body.length());
    }

    /** Operation of the request being handled (relay thread only), shown as the flow label. */
    private String lastOp = "request";

    private void respond(Socket c, int code, String body) throws Exception {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        OutputStream out = c.getOutputStream();
        out.write(("HTTP/1.0 " + code + " X\r\nContent-Type: application/json\r\nContent-Length: " + b.length + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        out.write(b); out.flush();
    }

    private JSONObject dispatch(JSONObject msg, boolean sealed) throws Exception {
        if ("pair_request".equals(msg.optString("op"))) return pairRequest(msg);
        byte[] key = key();
        JSONObject cmd;
        if (key == null) {
            cmd = confirmPairing(msg);                       // first signed command proves knowledge of the on-screen code
            if (cmd == null) throw new SecurityException("not paired");
            key = key();
        } else {
            JSONObject viaPending = null;
            try {
                // After aead1 was negotiated, the current key is only accepted inside a sealed envelope;
                // a plaintext command can only be the first command of an owner-started re-pairing.
                if (!sealed && prefs.getBoolean("require_aead", false)) throw new SecurityException("encryption required");
                cmd = verify(key, msg);
            }
            catch (SecurityException e) {
                // Re-pairing: a fresh on-screen code may replace the old key, never the reverse.
                viaPending = pendingCode != null ? confirmPairing(msg) : null;
                if (viaPending == null) throw e;
                cmd = viaPending; key = key();
            }
        }
        String op = cmd.getString("op");
        lastOp = op;
        JSONObject params = new JSONObject();
        switch (op) {
            case "discover_capabilities": case "get_status": case "get_permissions":
                params = status(); break;
            case "start_discovery": {
                JSONObject p = cmd.getJSONObject("params");
                int seconds = p.getInt("seconds");
                if (!"ble".equals(p.optString("radio")) || seconds < 1 || seconds > MAX_SCAN_SECONDS) throw new SecurityException("bounds");
                if (!ownerEnabled()) throw new SecurityException("owner has not enabled scanning on this device");
                if (!foreground) throw new SecurityException("open the OpenBridge Companion app on the device to allow scans");
                params.put("observations", scan(seconds)); break;
            }
            case "stop_discovery": scanning = false; break;
            case "set_controls": {
                JSONArray in = cmd.getJSONObject("params").getJSONArray("controls");
                if (in.length() > MAX_CONTROLS) throw new SecurityException("bounds");
                JSONArray clean = new JSONArray();
                for (int i = 0; i < in.length(); i++) {
                    JSONObject c = in.getJSONObject(i);
                    String id = c.getString("control_id"), label = c.getString("label"), kind = c.optString("kind", "button");
                    if (!id.matches("[a-z0-9-]{4,40}") || label.isEmpty() || label.length() > 40) throw new SecurityException("bounds");
                    if (!kind.matches("button|confirm|status|label")) throw new SecurityException("bounds");
                    String value = c.has("value") ? c.getString("value") : null;
                    if (value != null && value.length() > 40) throw new SecurityException("bounds");
                    JSONObject o = new JSONObject().put("control_id", id).put("label", label).put("kind", kind);
                    if ("status".equals(kind)) o.put("value", value == null ? "" : value);
                    clean.put(o);
                }
                long revision = cmd.getJSONObject("params").optLong("revision", 0);
                if (revision < 0 || revision > 100000) throw new SecurityException("bounds");
                synchronized (requests) { controls = clean; requests.clear(); pending.clear(); pendingControls.clear(); }
                prefs.edit().putString("controls", clean.toString()).putLong("layout_revision", revision).apply();
                ui.controls(clean); break;
            }
            case "update_status": {
                // Status values only: pending presses and the layout stay as they are.
                JSONObject vals = cmd.getJSONObject("params").getJSONObject("values");
                if (vals.length() == 0 || vals.length() > MAX_CONTROLS) throw new SecurityException("bounds");
                JSONArray cs;
                synchronized (requests) {
                    cs = controls();
                    for (int i = 0; i < cs.length(); i++) {
                        JSONObject c = cs.getJSONObject(i);
                        String id = c.optString("control_id");
                        if ("status".equals(c.optString("kind")) && vals.has(id)) {
                            String v = vals.getString(id);
                            if (v.length() > 40) throw new SecurityException("bounds");
                            c.put("value", v);
                        }
                    }
                }
                prefs.edit().putString("controls", cs.toString()).apply();
                ui.controls(cs); break;
            }
            case "get_requests": {
                JSONArray out = new JSONArray();
                long now = System.currentTimeMillis();
                synchronized (requests) {
                    while (!requests.isEmpty()) { JSONObject r = requests.poll(); out.put(r); pending.put(r.getString("request_id"), now); pendingControls.put(r.getString("request_id"), r.optString("control_id")); }
                }
                params.put("requests", out);
                if (renderedRevision >= 0) params.put("applied_revision", renderedRevision);
                break;
            }
            case "report_result": {
                JSONObject p = cmd.getJSONObject("params");
                String text = p.optString("text", "");
                synchronized (requests) { pendingControls.remove(p.optString("request_id")); if (pending.remove(p.optString("request_id")) == null) break; }   // unknown or late: ignored
                ui.result(text.length() > 80 ? text.substring(0, 80) : text); break;
            }
            case "get_commands": {
                JSONArray out = new JSONArray();
                synchronized (commands) {
                    while (!commands.isEmpty()) { JSONObject r = commands.poll(); out.put(r); pendingCommands.add(r.getString("request_id")); }
                }
                params.put("commands", out); break;
            }
            case "report_command": {
                JSONObject p = cmd.getJSONObject("params");
                String text = p.optString("text", "");
                boolean voice;
                synchronized (commands) {
                    if (!pendingCommands.remove(p.optString("request_id"))) break;   // unknown or late: ignored
                    voice = voiceRequests.remove(p.optString("request_id"));
                    if (voice) {   // clip served its purpose: drop the bytes
                        String drop = null;
                        for (Map.Entry<String, String> e : clipRequest.entrySet())
                            if (p.optString("request_id").equals(e.getValue())) { drop = e.getKey(); break; }
                        if (drop != null) { clips.remove(drop); clipRequest.remove(drop); }
                    }
                }
                ui.commandResult(text.length() > 160 ? text.substring(0, 160) : text, voice); break;
            }
            case "revoke_access": unpair(); break;
            default: throw new SecurityException("unknown op");
        }
        return signed(key, cmd.getString("relay_id"), params);
    }

    private JSONObject status() throws Exception {
        JSONObject perms = new JSONObject();
        perms.put("BLUETOOTH_SCAN", scanPermission()).put("owner_enabled", ownerEnabled()).put("bluetooth_on", bluetoothOn()).put("location_on", locationOn()).put("bluetooth_service", bluetoothServiceEnabled());
        JSONArray caps = new JSONArray();
        if (bleHardware()) caps.put("ble_scan");
        caps.put("remote_controls");
        caps.put("command_submit");
        caps.put(Aead.VERSION);
        boolean tv = ctx.getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK);
        return new JSONObject().put("capabilities", caps).put("permissions", perms).put("battery_powered", !tv)
                .put("sdk", Build.VERSION.SDK_INT).put("television", tv).put("full_control", fullControl());
    }

    private synchronized JSONObject pairRequest(JSONObject msg) throws Exception {
        if (failedPairing >= 5) throw new SecurityException("pairing locked; reopen the app");
        String pcNonce = msg.optString("pc_nonce");
        if (!pcNonce.matches("[0-9a-f]{16,64}")) throw new SecurityException("bad nonce");
        pendingCode = String.format("%06d", random.nextInt(1_000_000));
        pendingRelayNonce = hex(bytes(16)); pendingPcNonce = pcNonce; pendingUntil = System.currentTimeMillis() + 120_000;
        ui.code(pendingCode);
        return new JSONObject().put("protocol", PROTOCOL).put("relay_id", relayId()).put("relay_nonce", pendingRelayNonce).put("declared", status());
    }

    private byte[] key() {
        String k = prefs.getString("key", null);
        if (k != null) return unhex(k);
        return null;
    }

    private JSONObject verify(byte[] key, JSONObject msg) throws Exception {
        String mac = msg.optString("mac");
        JSONObject body = new JSONObject(msg.toString()); body.remove("mac");
        if (!MessageDigest.isEqual(hex(hmac(key, Canon.of(body))).getBytes(), mac.getBytes())) throw new SecurityException("bad signature");
        long now = System.currentTimeMillis() / 1000;
        if (!PROTOCOL.equals(body.optString("protocol")) || now < body.getLong("issued_at") - 5 || now > body.getLong("expires_at")) throw new SecurityException("expired");
        String nonce = body.getString("nonce");
        synchronized (seen) {
            if (seen.containsKey(nonce)) throw new SecurityException("replay");
            seen.values().removeIf(exp -> exp < now);
            if (seen.size() >= MAX_NONCES) throw new SecurityException("too many live commands");
            seen.put(nonce, body.getLong("expires_at"));
        }
        return body;
    }

    /** First signed command after pair_request proves the PC knows the code shown on this screen. */
    private synchronized JSONObject confirmPairing(JSONObject msg) throws Exception {
        if (pendingCode == null || System.currentTimeMillis() > pendingUntil) return null;
        byte[] k = derive(pendingCode, pendingRelayNonce, pendingPcNonce);
        JSONObject body;
        try { body = verify(k, msg); } catch (SecurityException e) { failedPairing++; return null; }
        // Pairing with the on-screen code is the owner's consent: scans are enabled right away (pausable in the app).
        prefs.edit().putString("key", hex(k)).putBoolean("owner_enabled", true).putBoolean("require_aead", false).apply(); pendingCode = null; ui.code(null);
        synchronized (seen) { seen.clear(); replies.clear(); }   // fresh pairing = fresh message space
        ui.status("Paired with OpenBridge. Bluetooth scans are available while this app is open.");
        return body;
    }

    private JSONObject signed(byte[] key, String relayId, JSONObject params) throws Exception {
        long now = System.currentTimeMillis() / 1000;
        JSONObject r = new JSONObject().put("protocol", PROTOCOL).put("relay_id", relayId).put("op", "reply").put("params", params)
                .put("nonce", hex(bytes(12))).put("issued_at", now).put("expires_at", now + 30);
        return r.put("mac", hex(hmac(key, Canon.of(r))));
    }

    @SuppressLint("MissingPermission")
    private JSONArray scan(int seconds) throws Exception {
        if (!bleHardware()) throw new SecurityException("no BLE hardware");
        if (!scanPermission()) throw new SecurityException("BLE scan permission not granted on this device");
        BluetoothManager m = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter a = m.getAdapter();
        if (!bluetoothServiceEnabled()) throw new SecurityException("The system Bluetooth app is disabled on this device");
        if (a == null || !a.isEnabled()) throw new SecurityException("Bluetooth is off on this device");
        if (!locationOn()) throw new SecurityException("Location is off; Android 11 and older require it for Bluetooth scans");
        BluetoothLeScanner s = a.getBluetoothLeScanner();
        Map<String, JSONObject> found = new LinkedHashMap<>();
        ScanCallback cb = new ScanCallback() {
            @Override public void onScanResult(int type, ScanResult r) {
                synchronized (found) {
                    if (found.size() >= MAX_OBSERVATIONS && !found.containsKey(r.getDevice().getAddress())) return;
                    try {
                        JSONObject o = new JSONObject().put("address", r.getDevice().getAddress()).put("rssi", r.getRssi());
                        if (r.getScanRecord() != null) {
                            String name = r.getScanRecord().getDeviceName();
                            if (name != null) o.put("name", name.length() > 60 ? name.substring(0, 60) : name);
                            JSONArray ids = new JSONArray(); SparseArray<byte[]> md = r.getScanRecord().getManufacturerSpecificData();
                            for (int i = 0; md != null && i < md.size() && i < 8; i++) ids.put(md.keyAt(i));
                            o.put("company_ids", ids);
                            JSONArray uu = new JSONArray();
                            if (r.getScanRecord().getServiceUuids() != null) for (ParcelUuid u : r.getScanRecord().getServiceUuids()) { if (uu.length() < 12) uu.put(u.toString()); }
                            o.put("service_uuids", uu);
                        }
                        found.put(r.getDevice().getAddress(), o);
                    } catch (Exception ignored) { }
                }
            }
        };
        scanning = true;
        ui.status("Scanning Bluetooth LE for " + seconds + " s at OpenBridge's request…");
        s.startScan(null, new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), cb);
        long end = System.currentTimeMillis() + seconds * 1000L;
        while (scanning && System.currentTimeMillis() < end) Thread.sleep(100);
        s.stopScan(cb); scanning = false;
        ui.status("Scan finished. " + found.size() + " advertiser(s) reported to OpenBridge.");
        JSONArray out = new JSONArray(); synchronized (found) { for (JSONObject o : found.values()) out.put(o); }
        return out;
    }

    static byte[] derive(String code, String relayNonce, String pcNonce) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(code.toCharArray(), (relayNonce + pcNonce).getBytes(StandardCharsets.UTF_8), 200_000, 256);
        return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
    }
    static byte[] hmac(byte[] key, String body) throws Exception {
        Mac m = Mac.getInstance("HmacSHA256"); m.init(new SecretKeySpec(key, "HmacSHA256")); return m.doFinal(body.getBytes(StandardCharsets.UTF_8));
    }
    private byte[] bytes(int n) { byte[] b = new byte[n]; random.nextBytes(b); return b; }
    static String hex(byte[] b) { StringBuilder s = new StringBuilder(); for (byte x : b) s.append(String.format("%02x", x)); return s.toString(); }
    static byte[] unhex(String s) { byte[] b = new byte[s.length() / 2]; for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16); return b; }
}
