package fr.openbridge.companion;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.ParcelUuid;
import android.util.Base64;
import java.util.ArrayDeque;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONObject;

/** The phone holds the Bluetooth link to ActiveLook / ENGO glasses for a paired PC that has no Bluetooth.
 *
 *  Scope, by construction: only a device exposing the ActiveLook service is kept connected; the PC can only write
 *  to the ActiveLook RX characteristic and only receives the flow-control and gesture notifications. Nothing else on
 *  the Bluetooth side is reachable through the relay. One link at a time; any unpair drops it. */
final class GlassesLink {
    static final UUID SERVICE = UUID.fromString("0783b03e-8535-b5a0-7140-a304d2495cb7");
    static final UUID RX = UUID.fromString("0783b03e-8535-b5a0-7140-a304d2495cba");
    static final UUID FLOW = UUID.fromString("0783b03e-8535-b5a0-7140-a304d2495cb9");
    static final UUID GESTURE = UUID.fromString("0783b03e-8535-b5a0-7140-a304d2495cbb");   // hand wave (sensor)
    static final UUID TOUCH = UUID.fromString("0783b03e-8535-b5a0-7140-a304d2495cbc");     // tap on the temple (ENGO 3)
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    static final int MAX_CHUNKS = 64, MAX_BATCH = 8192, MAX_EVENTS = 64, WANT_MTU = 247;

    private final Context ctx;
    private final Object lock = new Object();          // guards state below and one GATT operation at a time
    private final ArrayDeque<JSONObject> events = new ArrayDeque<>();
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic rx;
    private volatile String state = "IDLE", name = "", address = "", error = "";
    private volatile int mtu = 23;
    private volatile int opStatus;                     // result of the GATT operation being waited on
    private volatile boolean opDone;
    private long written, writeErrors, gestures;
    interface Listener { void changed(String state, String name); }
    private volatile Listener listener;

    GlassesLink(Context ctx) { this.ctx = ctx.getApplicationContext(); }
    void setListener(Listener l) { listener = l; }

    boolean connectPermission() {
        return Build.VERSION.SDK_INT < 31 || ctx.checkSelfPermission("android.permission.BLUETOOTH_CONNECT") == PackageManager.PERMISSION_GRANTED;
    }

    JSONObject status() throws Exception {
        return new JSONObject().put("state", state).put("name", name).put("address", address).put("mtu", mtu)
                .put("written", written).put("write_errors", writeErrors).put("gestures", gestures)
                .put("error", error).put("permission", connectPermission());
    }

    private void setState(String s) {
        state = s;
        Listener l = listener;
        if (l != null) try { l.changed(s, name); } catch (Exception ignored) { }
    }

    private void event(JSONObject e) {
        synchronized (events) {
            if (events.size() >= MAX_EVENTS) events.pollFirst();   // oldest dropped; gestures are not commands
            events.add(e);
            events.notifyAll();
        }
    }

    private final BluetoothGattCallback cb = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt g, int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) { done(0); return; }
            if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                boolean wasReady = "READY".equals(state);
                error = "disconnected (status " + status + ")";
                setState("DISCONNECTED");
                try { g.close(); } catch (Exception ignored) { }
                synchronized (lock) { if (gatt == g) { gatt = null; rx = null; } }
                try { event(new JSONObject().put("t", "state").put("v", "DISCONNECTED")); } catch (Exception ignored) { }
                if (!wasReady) done(status == 0 ? -1 : status);
            }
        }
        @Override public void onServicesDiscovered(BluetoothGatt g, int status) { done(status); }
        @Override public void onMtuChanged(BluetoothGatt g, int m, int status) { if (status == BluetoothGatt.GATT_SUCCESS) mtu = m; done(0); }
        @Override public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor d, int status) { done(status); }
        @Override public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int status) { done(status); }
        @SuppressWarnings("deprecation")
        @Override public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c) { changed(c.getUuid(), c.getValue()); }
        @Override public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c, byte[] value) { changed(c.getUuid(), value); }
    };

    private void changed(UUID u, byte[] v) {
        try {
            if (GESTURE.equals(u)) { gestures++; event(new JSONObject().put("t", "gesture").put("v", hexOf(v))); }
            else if (TOUCH.equals(u)) { gestures++; event(new JSONObject().put("t", "touch").put("v", hexOf(v))); }
            else if (FLOW.equals(u) && v != null && v.length > 0) event(new JSONObject().put("t", "flow").put("v", v[0] & 0xff));
        } catch (Exception ignored) { }
    }

    private static String hexOf(byte[] v) { StringBuilder b = new StringBuilder(); if (v != null) for (int i = 0; i < v.length && i < 8; i++) b.append(String.format("%02x", v[i])); return b.toString(); }

    private void done(int status) { synchronized (lock) { opStatus = status; opDone = true; lock.notifyAll(); } }

    /** Wait for the pending GATT callback. Caller holds `lock` and cleared opDone before starting the operation. */
    private int await(long ms, String what) throws Exception {
        long end = System.currentTimeMillis() + ms;
        while (!opDone) {
            long rem = end - System.currentTimeMillis();
            if (rem <= 0) throw new SecurityException("glasses: " + what + " timed out");
            lock.wait(rem);
        }
        return opStatus;
    }

    @SuppressLint("MissingPermission")
    JSONObject connect(String wantAddress, String nameHint, int seconds) throws Exception {
        if (!connectPermission()) throw new SecurityException("Allow Nearby devices (Bluetooth) for OpenBridge on the phone");
        BluetoothManager m = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter a = m == null ? null : m.getAdapter();
        if (a == null || !a.isEnabled()) throw new SecurityException("Bluetooth is off on this phone");
        synchronized (lock) {
            if (gatt != null && "READY".equals(state)) return status();
            disconnectLocked();
            error = ""; setState("SEARCHING");
        }
        BluetoothDevice dev = null;
        if (wantAddress != null && BluetoothAdapter.checkBluetoothAddress(wantAddress)) dev = a.getRemoteDevice(wantAddress);
        if (dev == null) {
            for (BluetoothDevice d : m.getConnectedDevices(BluetoothProfile.GATT)) if (match(d.getName(), nameHint)) { dev = d; break; }
        }
        if (dev == null) dev = scan(a, nameHint, seconds);
        if (dev == null) { setState("NOT_FOUND"); error = "no ENGO glasses advertising (on, and not connected to another app?)"; throw new SecurityException(error); }
        address = dev.getAddress(); name = dev.getName() == null ? "" : dev.getName();
        synchronized (lock) {
            setState("CONNECTING");
            opDone = false;
            gatt = Build.VERSION.SDK_INT >= 23 ? dev.connectGatt(ctx, false, cb, BluetoothDevice.TRANSPORT_LE) : dev.connectGatt(ctx, false, cb);
            try {
                if (await(8_000, "connect") != 0) throw new SecurityException("glasses: connection refused");
                opDone = false;
                if (!gatt.discoverServices()) throw new SecurityException("glasses: service discovery failed");
                if (await(5_000, "service discovery") != 0) throw new SecurityException("glasses: service discovery failed");
                BluetoothGattService s = gatt.getService(SERVICE);
                if (s == null) throw new SecurityException("this device is not ActiveLook / ENGO glasses");   // scope check
                rx = s.getCharacteristic(RX);
                if (rx == null) throw new SecurityException("glasses: RX characteristic missing");
                opDone = false;
                if (gatt.requestMtu(WANT_MTU)) { try { await(2_000, "MTU"); } catch (SecurityException ignored) { } }
                for (UUID u : new UUID[]{FLOW, GESTURE, TOUCH}) subscribe(s.getCharacteristic(u));
                try { gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH); } catch (Exception ignored) { }
                setState("READY");
                synchronized (events) { events.clear(); }
                return status();
            } catch (Exception e) {
                error = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                disconnectLocked(); setState("FAILED");
                throw e instanceof SecurityException ? (SecurityException) e : new SecurityException("glasses: " + error);
            }
        }
    }

    @SuppressLint("MissingPermission")
    @SuppressWarnings("deprecation")
    private void subscribe(BluetoothGattCharacteristic c) throws Exception {
        if (c == null) return;
        gatt.setCharacteristicNotification(c, true);
        BluetoothGattDescriptor d = c.getDescriptor(CCCD);
        if (d == null) return;
        opDone = false;
        boolean started;
        if (Build.VERSION.SDK_INT >= 33) started = gatt.writeDescriptor(d, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == BluetoothGatt.GATT_SUCCESS;
        else { d.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); started = gatt.writeDescriptor(d); }
        if (started) await(2_000, "subscribe");
    }

    private static boolean match(String n, String hint) {
        if (n == null) return false;
        String h = hint == null || hint.isEmpty() ? "ENGO" : hint;
        return n.toUpperCase().startsWith(h.toUpperCase());
    }

    @SuppressLint("MissingPermission")
    private BluetoothDevice scan(BluetoothAdapter a, String hint, int seconds) throws Exception {
        BluetoothLeScanner s = a.getBluetoothLeScanner();
        if (s == null) return null;
        final BluetoothDevice[] found = new BluetoothDevice[1];
        ScanCallback sc = new ScanCallback() {
            @Override public void onScanResult(int type, ScanResult r) {
                boolean svc = false;
                if (r.getScanRecord() != null && r.getScanRecord().getServiceUuids() != null)
                    for (ParcelUuid u : r.getScanRecord().getServiceUuids()) svc |= SERVICE.equals(u.getUuid());
                String n = r.getScanRecord() != null ? r.getScanRecord().getDeviceName() : null;
                if (svc || match(n, hint)) synchronized (found) { if (found[0] == null) { found[0] = r.getDevice(); found.notifyAll(); } }
            }
        };
        s.startScan(null, new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), sc);
        try {
            synchronized (found) {
                long end = System.currentTimeMillis() + Math.max(1, Math.min(15, seconds)) * 1000L;
                while (found[0] == null) { long rem = end - System.currentTimeMillis(); if (rem <= 0) break; found.wait(rem); }
            }
        } finally { try { s.stopScan(sc); } catch (Exception ignored) { } }
        return found[0];
    }

    /** Write a batch of ActiveLook frame chunks, in order, each one waiting for the stack before the next. */
    @SuppressLint("MissingPermission")
    @SuppressWarnings("deprecation")
    JSONObject write(JSONArray chunks) throws Exception {
        if (chunks == null || chunks.length() > MAX_CHUNKS) throw new SecurityException("bounds");
        byte[][] data = new byte[chunks.length()][];
        int total = 0;
        for (int i = 0; i < data.length; i++) {
            data[i] = Base64.decode(chunks.getString(i), Base64.NO_WRAP);
            total += data[i].length;
            if (data[i].length == 0 || data[i].length > Math.max(20, mtu - 3) || total > MAX_BATCH) throw new SecurityException("bounds");
        }
        int ok = 0;
        synchronized (lock) {
            if (gatt == null || rx == null || !"READY".equals(state)) throw new SecurityException("glasses not connected");
            for (byte[] d : data) {
                opDone = false;
                boolean started;
                if (Build.VERSION.SDK_INT >= 33) started = gatt.writeCharacteristic(rx, d, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) == BluetoothGatt.GATT_SUCCESS;
                else { rx.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE); rx.setValue(d); started = gatt.writeCharacteristic(rx); }
                if (!started) { writeErrors++; break; }
                try { if (await(2_000, "write") != 0) { writeErrors++; break; } } catch (SecurityException e) { writeErrors++; break; }
                ok++; written++;
            }
        }
        JSONObject r = status().put("accepted", ok);
        r.put("events", drain(0));
        return r;
    }

    /** Notifications from the glasses (gestures, flow control, link state), waiting up to waitMs for the first one. */
    JSONArray drain(int waitMs) throws Exception {
        JSONArray out = new JSONArray();
        synchronized (events) {
            if (events.isEmpty() && waitMs > 0) {
                long end = System.currentTimeMillis() + waitMs;
                while (events.isEmpty()) { long rem = end - System.currentTimeMillis(); if (rem <= 0) break; events.wait(rem); }
            }
            while (!events.isEmpty()) out.put(events.poll());
        }
        return out;
    }

    /** A navigation button pressed on the phone (next, ok, back, home): delivered with the glasses' own events. */
    void button(String ev) {
        if (!"READY".equals(state) || !ev.matches("next|ok|back|home")) return;
        try { event(new JSONObject().put("t", "button").put("v", ev)); } catch (Exception ignored) { }
    }

    String state() { return state; }

    void disconnect() { synchronized (lock) { disconnectLocked(); } setState("IDLE"); }

    @SuppressLint("MissingPermission")
    private void disconnectLocked() {
        BluetoothGatt g = gatt; gatt = null; rx = null; mtu = 23;
        if (g != null) { try { g.disconnect(); } catch (Exception ignored) { } try { g.close(); } catch (Exception ignored) { } }
    }
}
