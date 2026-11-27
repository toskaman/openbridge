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
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.ParcelUuid;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** The phone as a sensor for the glasses' sport and navigation screens: GPS, compass, a fall alert from the
 *  accelerometer, and Bluetooth sport sensors (heart rate, running speed, cycling speed / cadence, power, smart
 *  trainers) held by the phone. Raw sensor values go to the PC unchanged; it decodes them with the same code as
 *  sensors connected to the PC (src/glasses/sensors.py).
 *
 *  Off by default: runs only while the owner has the Sensors module on and has started it (Sensors page). The
 *  values leave the phone only to the paired PC, over the signed and encrypted relay (op get_sensors). */
final class PhoneSensors {
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    /** kind -> {service, measurement characteristic}. */
    static final Map<String, UUID[]> KINDS = new HashMap<>();
    static {
        KINDS.put("heart_rate", new UUID[]{u16(0x180D), u16(0x2A37)});
        KINDS.put("rsc", new UUID[]{u16(0x1814), u16(0x2A53)});
        KINDS.put("csc", new UUID[]{u16(0x1816), u16(0x2A5B)});
        KINDS.put("power", new UUID[]{u16(0x1818), u16(0x2A63)});
        KINDS.put("trainer", new UUID[]{u16(0x1826), u16(0x2AD2)});
    }
    static UUID u16(int v) { return UUID.fromString(String.format("%08x-0000-1000-8000-00805f9b34fb", v)); }

    private static PhoneSensors instance;
    static synchronized PhoneSensors get(Context c) { if (instance == null) instance = new PhoneSensors(c.getApplicationContext()); return instance; }

    private final Context ctx;
    private final SharedPreferences prefs;
    private HandlerThread thread;
    private Handler handler;
    private volatile boolean running;
    private volatile Location location;
    private volatile float heading = Float.NaN;
    private volatile long headingAt, fallAt;
    private final Map<String, JSONObject> readings = new HashMap<>();      // kind -> {raw, name, at, hr?}
    private final Map<String, BluetoothGatt> gatts = new HashMap<>();
    private long bigShakeAt;

    private PhoneSensors(Context c) {
        ctx = c;
        prefs = c.getSharedPreferences("sensors", Context.MODE_PRIVATE);
    }

    boolean running() { return running; }
    boolean locationPermission() { return ctx.checkSelfPermission("android.permission.ACCESS_FINE_LOCATION") == PackageManager.PERMISSION_GRANTED; }
    boolean blePermission() {
        return Build.VERSION.SDK_INT < 31 || (ctx.checkSelfPermission("android.permission.BLUETOOTH_CONNECT") == PackageManager.PERMISSION_GRANTED
                && ctx.checkSelfPermission("android.permission.BLUETOOTH_SCAN") == PackageManager.PERMISSION_GRANTED);
    }

    /** Saved sport sensors: address -> "kind|name". */
    Map<String, String> saved() {
        Map<String, String> out = new HashMap<>();
        for (String s : prefs.getStringSet("devices", new HashSet<>())) { String[] a = s.split("\\|", 3); if (a.length == 3) out.put(a[0], a[1] + "|" + a[2]); }
        return out;
    }
    void save(String address, String kind, String name) {
        Set<String> set = new HashSet<>(prefs.getStringSet("devices", new HashSet<>()));
        set.removeIf(x -> x.startsWith(address + "|"));
        set.add(address + "|" + kind + "|" + name.replace("|", " "));
        prefs.edit().putStringSet("devices", set).apply();
        if (running) handler.post(() -> connect(address, kind, name));
    }
    void forget(String address) {
        Set<String> set = new HashSet<>(prefs.getStringSet("devices", new HashSet<>()));
        set.removeIf(x -> x.startsWith(address + "|"));
        prefs.edit().putStringSet("devices", set).apply();
        BluetoothGatt g;
        synchronized (gatts) { g = gatts.remove(address); }
        if (g != null) closeGatt(g);
    }

    boolean sportSensorConnected() {
        long now = System.currentTimeMillis();
        synchronized (readings) { for (JSONObject r : readings.values()) if (now - r.optLong("at") < 30_000) return true; }
        return false;
    }

    @SuppressLint("MissingPermission")
    synchronized void start() {
        if (running) return;
        running = true;
        thread = new HandlerThread("phone-sensors");
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.post(() -> {
            if (locationPermission()) {
                LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
                try { if (lm != null) lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, gps, thread.getLooper()); } catch (Exception e) { Diag.log("GPS: " + e.getMessage()); }
            }
            SensorManager sm = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
            if (sm != null) {
                Sensor rv = sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR), acc = sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
                if (rv != null) sm.registerListener(motion, rv, SensorManager.SENSOR_DELAY_UI, handler);
                if (acc != null) sm.registerListener(motion, acc, SensorManager.SENSOR_DELAY_GAME, handler);
            }
            for (Map.Entry<String, String> e : saved().entrySet()) { String[] kn = e.getValue().split("\\|", 2); connect(e.getKey(), kn[0], kn[1]); }
        });
        Diag.log("phone sensors started");
    }

    @SuppressLint("MissingPermission")
    synchronized void stop() {
        if (!running) return;
        running = false;
        LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
        try { if (lm != null) lm.removeUpdates(gps); } catch (Exception ignored) { }
        SensorManager sm = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
        if (sm != null) sm.unregisterListener(motion);
        synchronized (gatts) { for (BluetoothGatt g : gatts.values()) closeGatt(g); gatts.clear(); }
        thread.quitSafely();
        Diag.log("phone sensors stopped");
    }

    private final LocationListener gps = new LocationListener() {
        @Override public void onLocationChanged(Location l) { location = l; }
        @Override public void onStatusChanged(String p, int s, Bundle b) { }
        @Override public void onProviderEnabled(String p) { }
        @Override public void onProviderDisabled(String p) { }
    };

    private final float[] rot = new float[9], orient = new float[3];
    private final SensorEventListener motion = new SensorEventListener() {
        @Override public void onSensorChanged(SensorEvent e) {
            if (e.sensor.getType() == Sensor.TYPE_ROTATION_VECTOR) {
                SensorManager.getRotationMatrixFromVector(rot, e.values);
                SensorManager.getOrientation(rot, orient);
                heading = (float) ((Math.toDegrees(orient[0]) + 360) % 360);
                headingAt = System.currentTimeMillis();
            } else {
                // Fall: a hard shock (over ~3 g), then the phone lying still for 2 s.
                double g = Math.sqrt(e.values[0] * e.values[0] + e.values[1] * e.values[1] + e.values[2] * e.values[2]) / 9.81;
                long now = System.currentTimeMillis();
                if (g > 3.0) bigShakeAt = now;
                else if (bigShakeAt > 0 && now - bigShakeAt > 2000 && now - bigShakeAt < 4000 && Math.abs(g - 1.0) < 0.15) {
                    fallAt = now; bigShakeAt = 0; Diag.log("possible fall detected");
                }
            }
        }
        @Override public void onAccuracyChanged(Sensor s, int a) { }
    };

    // ---- Bluetooth sport sensors -------------------------------------------------------------------
    interface Found { void found(String address, String name, String kind); }

    /** Scan 10 s for sport sensors; each one found is reported once. */
    @SuppressLint("MissingPermission")
    void scan(Found cb) {
        BluetoothManager m = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter a = m == null ? null : m.getAdapter();
        BluetoothLeScanner s = a == null || !a.isEnabled() ? null : a.getBluetoothLeScanner();
        if (s == null || !blePermission()) return;
        List<ScanFilter> filters = new ArrayList<>();
        for (UUID[] k : KINDS.values()) filters.add(new ScanFilter.Builder().setServiceUuid(new ParcelUuid(k[0])).build());
        Set<String> seen = new HashSet<>();
        ScanCallback sc = new ScanCallback() {
            @Override public void onScanResult(int type, ScanResult r) {
                if (r.getScanRecord() == null || r.getScanRecord().getServiceUuids() == null) return;
                String addr = r.getDevice().getAddress();
                if (!seen.add(addr)) return;
                String kind = null;
                for (ParcelUuid u : r.getScanRecord().getServiceUuids())
                    for (Map.Entry<String, UUID[]> k : KINDS.entrySet()) if (k.getValue()[0].equals(u.getUuid())) kind = k.getKey();
                String name = r.getScanRecord().getDeviceName();
                if (kind != null) cb.found(addr, name == null ? addr : name, kind);
            }
        };
        s.startScan(filters, new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), sc);
        new Handler(android.os.Looper.getMainLooper()).postDelayed(() -> { try { s.stopScan(sc); } catch (Exception ignored) { } }, 10_000);
    }

    @SuppressLint("MissingPermission")
    private void connect(String address, String kind, String name) {
        if (!blePermission() || !KINDS.containsKey(kind)) return;
        BluetoothManager m = (BluetoothManager) ctx.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter a = m == null ? null : m.getAdapter();
        if (a == null || !a.isEnabled() || !BluetoothAdapter.checkBluetoothAddress(address)) return;
        synchronized (gatts) { if (gatts.containsKey(address)) return; }
        BluetoothDevice d = a.getRemoteDevice(address);
        final UUID[] k = KINDS.get(kind);
        BluetoothGatt g = d.connectGatt(ctx, true, new BluetoothGattCallback() {
            @Override public void onConnectionStateChange(BluetoothGatt gt, int status, int st) {
                if (st == BluetoothProfile.STATE_CONNECTED) gt.discoverServices();
                else if (st == BluetoothProfile.STATE_DISCONNECTED) Diag.log("sensor " + name + " disconnected");
            }
            @SuppressWarnings("deprecation")
            @Override public void onServicesDiscovered(BluetoothGatt gt, int status) {
                BluetoothGattService svc = gt.getService(k[0]);
                BluetoothGattCharacteristic ch = svc == null ? null : svc.getCharacteristic(k[1]);
                if (ch == null) return;
                gt.setCharacteristicNotification(ch, true);
                BluetoothGattDescriptor dsc = ch.getDescriptor(CCCD);
                if (dsc == null) return;
                byte[] val = (ch.getProperties() & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0 && (ch.getProperties() & BluetoothGattCharacteristic.PROPERTY_NOTIFY) == 0
                        ? BluetoothGattDescriptor.ENABLE_INDICATION_VALUE : BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE;
                if (Build.VERSION.SDK_INT >= 33) gt.writeDescriptor(dsc, val); else { dsc.setValue(val); gt.writeDescriptor(dsc); }
                Diag.log("sensor " + name + " connected (" + kind + ")");
            }
            @SuppressWarnings("deprecation")
            @Override public void onCharacteristicChanged(BluetoothGatt gt, BluetoothGattCharacteristic c) { reading(kind, name, c.getValue()); }
            @Override public void onCharacteristicChanged(BluetoothGatt gt, BluetoothGattCharacteristic c, byte[] v) { reading(kind, name, v); }
        }, BluetoothDevice.TRANSPORT_LE);
        synchronized (gatts) { gatts.put(address, g); }
    }

    @SuppressLint("MissingPermission")
    private static void closeGatt(BluetoothGatt g) { try { g.disconnect(); } catch (Exception ignored) { } try { g.close(); } catch (Exception ignored) { } }

    private void reading(String kind, String name, byte[] v) {
        if (v == null || v.length == 0) return;
        StringBuilder hex = new StringBuilder();
        for (byte b : v) hex.append(String.format("%02x", b));
        try {
            JSONObject r = new JSONObject().put("kind", kind).put("name", name).put("raw", hex.toString()).put("at", System.currentTimeMillis());
            if ("heart_rate".equals(kind) && v.length >= 2) r.put("bpm", (v[0] & 1) != 0 && v.length >= 3 ? ((v[1] & 0xff) | ((v[2] & 0xff) << 8)) : (v[1] & 0xff));
            synchronized (readings) { readings.put(kind, r); }
        } catch (Exception ignored) { }
    }

    /** Latest values: location, heading, sport sensors, fall alert. Ages in seconds so the PC can drop stale data. */
    JSONObject snapshot() throws Exception {
        long now = System.currentTimeMillis();
        JSONObject o = new JSONObject().put("running", running);
        Location l = location;
        if (l != null) {
            JSONObject loc = new JSONObject().put("lat", l.getLatitude()).put("lon", l.getLongitude())
                    .put("age_s", (now - l.getTime()) / 1000.0).put("accuracy_m", l.hasAccuracy() ? l.getAccuracy() : -1);
            if (l.hasAltitude()) loc.put("alt_m", l.getAltitude());
            if (l.hasSpeed()) loc.put("speed_mps", l.getSpeed());
            if (l.hasBearing()) loc.put("bearing_deg", l.getBearing());
            o.put("location", loc);
        }
        if (!Float.isNaN(heading) && now - headingAt < 5000) o.put("heading_deg", Math.round(heading));
        JSONArray sens = new JSONArray();
        synchronized (readings) {
            for (JSONObject r : readings.values()) sens.put(new JSONObject(r.toString()).put("age_s", (now - r.optLong("at")) / 1000.0));
        }
        o.put("sport", sens);
        if (fallAt > 0) o.put("fall_age_s", (now - fallAt) / 1000.0);
        return o;
    }
}
