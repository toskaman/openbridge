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

    interface Ui { void status(String text); void code(String code); default void controls(JSONArray c) { } default void result(String text) { } }
    static final int MAX_CONTROLS = 12, MAX_QUEUE = 16;
    /** Owner-authorized controls pushed by the paired PC (label + id only; the PC keeps skill, target and params). */
    private JSONArray controls = new JSONArray();
    private final java.util.ArrayDeque<JSONObject> requests = new java.util.ArrayDeque<>();
    private long lastPress;
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
    private volatile boolean running;
    private static RelayServer instance;
    volatile boolean foreground;

    /** One relay per process: survives the activity being destroyed while a settings screen is open (low-RAM TVs). */
    static synchronized RelayServer get(Context ctx, Ui ui) {
        if (instance == null) instance = new RelayServer(ctx.getApplicationContext(), ui);
        instance.ui = ui;
        return instance;
    }
    private ServerSocket server;
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

    void unpair() { synchronized (requests) { controls = new JSONArray(); requests.clear(); } prefs.edit().remove("controls").apply();
        prefs.edit().remove("key").putBoolean("owner_enabled", false).apply(); ui.status("Pairing removed. This device no longer accepts commands."); }

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
                ui.status("Listening for OpenBridge on port " + PORT + (paired() ? " · paired" : " · not paired"));
                while (running) {
                    try (Socket c = s.accept()) { c.setSoTimeout(5000); handle(c); } catch (Exception ignored) { }
                }
            } catch (Exception e) { ui.status("Relay could not start: " + e.getClass().getSimpleName()); running = false; }
        }, "openbridge-relay").start();
    }

    void stop() { running = false; try { if (server != null) server.close(); } catch (Exception ignored) { } }

    private void handle(Socket c) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
        String line; int length = -1;
        String request = in.readLine();
        if (request == null || !request.startsWith("POST /ob ")) { respond(c, 404, "{\"error\":\"not found\"}"); return; }
        while ((line = in.readLine()) != null && !line.isEmpty()) {
            if (line.toLowerCase().startsWith("content-length:")) length = Integer.parseInt(line.substring(15).trim());
        }
        if (length < 0 || length > MAX_BODY) { respond(c, 413, "{\"error\":\"size\"}"); return; }
        char[] buf = new char[length]; int read = 0;
        while (read < length) { int n = in.read(buf, read, length - read); if (n < 0) break; read += n; }
        JSONObject msg = new JSONObject(new String(buf, 0, read));
        JSONObject reply;
        try { reply = dispatch(msg); } catch (SecurityException e) { respond(c, 403, new JSONObject().put("error", e.getMessage()).toString()); return; }
        respond(c, 200, reply.toString());
    }

    private void respond(Socket c, int code, String body) throws Exception {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        OutputStream out = c.getOutputStream();
        out.write(("HTTP/1.0 " + code + " X\r\nContent-Type: application/json\r\nContent-Length: " + b.length + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
        out.write(b); out.flush();
    }

    private JSONObject dispatch(JSONObject msg) throws Exception {
        if ("pair_request".equals(msg.optString("op"))) return pairRequest(msg);
        byte[] key = key();
        JSONObject cmd;
        if (key == null) {
            cmd = confirmPairing(msg);                       // first signed command proves knowledge of the on-screen code
            if (cmd == null) throw new SecurityException("not paired");
            key = key();
        } else {
            JSONObject viaPending = null;
            try { cmd = verify(key, msg); }
            catch (SecurityException e) {
                // Re-pairing: a fresh on-screen code may replace the old key, never the reverse.
                viaPending = pendingCode != null ? confirmPairing(msg) : null;
                if (viaPending == null) throw e;
                cmd = viaPending; key = key();
            }
        }
        String op = cmd.getString("op");
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
                    String id = c.getString("control_id"), label = c.getString("label");
                    if (!id.matches("[a-z0-9-]{4,40}") || label.isEmpty() || label.length() > 40) throw new SecurityException("bounds");
                    clean.put(new JSONObject().put("control_id", id).put("label", label));
                }
                synchronized (requests) { controls = clean; requests.clear(); pending.clear(); pendingControls.clear(); }
                prefs.edit().putString("controls", clean.toString()).apply();
                ui.controls(clean); break;
            }
            case "get_requests": {
                JSONArray out = new JSONArray();
                long now = System.currentTimeMillis();
                synchronized (requests) {
                    while (!requests.isEmpty()) { JSONObject r = requests.poll(); out.put(r); pending.put(r.getString("request_id"), now); pendingControls.put(r.getString("request_id"), r.optString("control_id")); }
                }
                params.put("requests", out); break;
            }
            case "report_result": {
                JSONObject p = cmd.getJSONObject("params");
                String text = p.optString("text", "");
                synchronized (requests) { pendingControls.remove(p.optString("request_id")); if (pending.remove(p.optString("request_id")) == null) break; }   // unknown or late: ignored
                ui.result(text.length() > 80 ? text.substring(0, 80) : text); break;
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
        boolean tv = ctx.getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK);
        return new JSONObject().put("capabilities", caps).put("permissions", perms).put("battery_powered", !tv)
                .put("sdk", Build.VERSION.SDK_INT).put("television", tv);
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
        prefs.edit().putString("key", hex(k)).putBoolean("owner_enabled", true).apply(); pendingCode = null; ui.code(null);
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
