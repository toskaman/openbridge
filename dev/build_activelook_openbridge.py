"""
OpenBridge Build Script for ActiveLook Official Android App with Emulator Bridge.
Patches bundle.js in ActiveLook base APK, rebuilds, aligns, and signs with OpenBridge keystore.
"""
import os
import pathlib
import subprocess
import zipfile

PROJECT_ROOT = pathlib.Path(r"Z:\Hackatons\OpenBridge")
SDK = pathlib.Path(r"D:\Android\sdk\build-tools\34.0.0")
KEYDIR = pathlib.Path(os.environ["LOCALAPPDATA"]) / "OpenBridge" / "companion-signing"
PW = (KEYDIR / "pass.txt").read_text(encoding="utf-8").strip()
KEYSTORE = KEYDIR / "companion.jks"

PATCH_JS = r"""
// --- OPENBRIDGE EMULATOR BRIDGE START ---
// v3 (2026-11-22): real ActiveLook command ids, layout bank, F01-F38 overlay (0xF0), logs kept out of Sentry.
// v2 fixes over v1:
//  1. Frames now use the real ActiveLook layout 0xFF CMD FMT LEN DATA 0xAA (LEN = whole frame),
//     which is what activelook_emulator.parse_frames() expects. v1 omitted FMT, so nothing rendered.
//  2. No JS Runnables on java.lang.Thread: this app does not set android.enableMultithreadedJavascript,
//     so NativeScript runs every JS callback on the UI thread anyway (Socket() -> NetworkOnMainThreadException,
//     blocking read() -> frozen UI). Socket work is now short and bounded on the UI thread
//     (connect timeout 1.5 s, SO_TIMEOUT 1 ms polled every 40 ms) with StrictMode relaxed only around each call.
class OpenBridgeSocketGlasses {
    constructor(logger, onDisconnected) {
        this.__logger = function(msg){ console.log("[OpenBridge] " + msg); };   // never the app logger (Sentry CSV)
        this._onDisconnected = onDisconnected;
        this._wrapper = null;
        this.socket = null;
        this.outStream = null;
        this.inStream = null;
        this._rx = [];
        this._poll = null;
        this._closed = false;
        this._sensorCb = null;
        this._batteryCb = null;
        this._flowCb = null;
        global.OpenBridgeActiveGlasses = this;
    }
    _log(m) { console.log("[OpenBridge] " + m); }
    _withNet(fn) {
        const SM = android.os.StrictMode;
        let old = null;
        try { old = SM.getThreadPolicy(); SM.setThreadPolicy(new SM.ThreadPolicy.Builder().permitAll().build()); } catch (e) {}
        try { return fn(); }
        finally { if (old) { try { SM.setThreadPolicy(old); } catch (e) {} } }
    }
    _isTimeout(e) {
        try { if (e && e.nativeException && e.nativeException instanceof java.net.SocketTimeoutException) return true; } catch (x) {}
        return String(e).indexOf("SocketTimeoutException") >= 0;
    }
    connectSocket(host, port, cb) {
        const self = this;
        this._host = host; this._port = port;
        setTimeout(function() {
            let ok = false;
            try {
                self._withNet(function() {
                    const s = new java.net.Socket();
                    s.setTcpNoDelay(true);
                    s.connect(new java.net.InetSocketAddress(host, port), 1500);
                    s.setSoTimeout(1);
                    self.socket = s;
                    self.outStream = s.getOutputStream();
                    self.inStream = s.getInputStream();
                });
                ok = true;
                self._closed = false;
                self._startPolling();
                self._log("[OpenBridgeSocket] Connected to " + host + ":" + port);
            } catch (e) {
                self._log("[OpenBridgeSocket] Connection error: " + e);
                self._closeQuietly();
            }
            if (cb) cb(ok);
        }, 0);
    }
    _frame(cmd, payload) {
        const n = payload.length + 5;
        if (n <= 255) return [0xFF, cmd & 0xFF, 0x00, n].concat(payload, [0xAA]);
        const w = payload.length + 6;
        return [0xFF, cmd & 0xFF, 0x20, (w >> 8) & 0xFF, w & 0xFF].concat(payload, [0xAA]);
    }
    // Callers pass the legacy v1 shape [0xFF, cmd, len, ...payload, 0xAA]; re-frame it properly.
    _sendRaw(legacy) {
        if (!this.outStream || this._closed) return;
        const payload = [];
        for (let i = 3; i < legacy.length - 1; i++) payload.push(legacy[i] & 0xFF);
        this._write(this._frame(legacy[1], payload));
    }
    _write(bytes) {
        const self = this;
        try {
            const jb = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, bytes.length);
            for (let i = 0; i < bytes.length; i++) { const v = bytes[i] & 0xFF; jb[i] = v > 127 ? v - 256 : v; }
            this._withNet(function() { self.outStream.write(jb); self.outStream.flush(); });
        } catch (err) {
            this._log("[OpenBridgeSocket] Write error: " + err);
            this._handleClosed();
        }
    }
    _startPolling() {
        const self = this;
        const buf = java.lang.reflect.Array.newInstance(java.lang.Byte.TYPE, 1024);
        if (this._poll) clearInterval(this._poll);
        this._poll = setInterval(function() {
            if (!self.inStream || self._closed) return;
            try {
                for (let guard = 0; guard < 16; guard++) {
                    let n = 0;
                    try { n = self._withNet(function() { return self.inStream.read(buf); }); }
                    catch (e) { if (self._isTimeout(e)) break; throw e; }
                    if (n < 0) { self._log("[OpenBridgeSocket] PC closed the connection"); self._handleClosed(); return; }
                    for (let i = 0; i < n; i++) self._rx.push(buf[i] & 0xFF);
                    if (n < 1024) break;
                }
                self._parseRx();
            } catch (e) {
                self._log("[OpenBridgeSocket] Reader error: " + e);
                self._handleClosed();
            }
        }, 40);
    }
    // PC -> phone: optical gesture 0xFF 0x0A 0x01 <byte> 0xAA (ActiveLookTCPServer.broadcast_gesture)
    _parseRx() {
        const rx = this._rx;
        let i = 0;
        while (i < rx.length) {
            if (rx[i] !== 0xFF) { i++; continue; }
            if (rx.length - i < 5) break;
            if (rx[i + 1] === 0x0A && rx[i + 4] === 0xAA) {
                this._log("[OpenBridgeSocket] Optical gesture received from PC (" + rx[i + 3] + ")");
                this._fireGesture();
                i += 5;
            } else {
                i++;
            }
        }
        this._rx = rx.slice(i);
        if (this._rx.length > 4096) this._rx = [];
    }
    _fireGesture() {
        const cb = this._sensorCb;
        try {
            if (typeof cb === "function") cb();
            else if (cb && cb.run) cb.run();
        } catch (e) { this._log("[OpenBridgeSocket] gesture callback error: " + e); }
    }
    _closeQuietly() {
        if (this._poll) { clearInterval(this._poll); this._poll = null; }
        const s = this.socket;
        this.socket = null; this.outStream = null; this.inStream = null;
        if (s) { try { this._withNet(function() { s.close(); }); } catch (e) {} }
    }
    // Sticky link: if HUD Studio goes away (restart, crash) keep the app "connected" and retry quietly,
    // then replay onConnected so the app redraws. Only app-initiated disconnects reach the app at once.
    _handleClosed() {
        if (this._closed) return;
        this._closed = true;
        this._closeQuietly();
        if (!this._userClosed && this._onConnected && this._host) { this._startRelink(); return; }
        this._notifyDisconnected();
    }
    _startRelink() {
        const self = this;
        if (this._relink) return;
        this._relinkSince = Date.now();
        this._log("[OpenBridgeSocket] link lost - retrying every 1.5 s");
        this._relink = setInterval(function() {
            if (self._userClosed) { clearInterval(self._relink); self._relink = null; return; }
            if (Date.now() - self._relinkSince > 600000) {
                clearInterval(self._relink); self._relink = null;
                self._log("[OpenBridgeSocket] relink abandoned after 10 min"); self._notifyDisconnected(); return;
            }
            if (self._connecting) return;
            self._connecting = true;
            self.connectSocket(self._host, self._port, function(ok) {
                self._connecting = false;
                if (!ok) { self._closed = true; return; }
                clearInterval(self._relink); self._relink = null;
                self._log("[OpenBridgeSocket] link restored");
                try { self._onConnected(self._wrapper || self); } catch (e) { self._log("[OpenBridgeSocket] onConnected replay failed: " + e); }
            });
        }, 1500);
    }
    _notifyDisconnected() {
        const cb = this._onDisconnected;
        try {
            if (typeof cb === "function") cb(this._wrapper || this);
            else if (cb && cb.accept) cb.accept(this);
        } catch (e) { this._log("[OpenBridgeSocket] onDisconnected error: " + e); }
    }
    getSerializedGlasses() { return new java.lang.String("OB-SERIALIZED-EMULATOR"); }
    getManufacturer() { return "Engo"; }
    getName() { return "ENGO 2 000001"; }
    getAddress() { return "OB:77:89:00:00:01"; }
    isFirmwareAtLeast(v) { return true; }
    compareFirmwareVersion(v) { return 0; }
    disconnect() {
        this._userClosed = true;
        if (this._relink) { clearInterval(this._relink); this._relink = null; this._notifyDisconnected(); return; }
        this._handleClosed();
    }
    setOnDisconnected(cb) { this._onDisconnected = cb; }
    getDeviceInformation() {
        return {
            getManufacturerName: function() { return "ENGO"; },
            getModelNumber: function() { return "ENGO 2"; },
            getSerialNumber: function() { return "000001"; },
            getFirmwareVersion: function() { return "4.2.0"; },
            getFirmwareRevision: function() { return "4.2.0"; },
            getHardwareRevision: function() { return "2.0"; },
            getSoftwareRevision: function() { return "4.2.0"; }
        };
    }
    subscribeToBatteryLevelNotifications(cb) { this._batteryCb = cb; if (cb && cb.accept) cb.accept(88); }
    subscribeToFlowControlNotifications(cb) { this._flowCb = cb; }
    subscribeToSensorInterfaceNotifications(cb) { this._sensorCb = cb; }
    unsubscribeToBatteryLevelNotifications() { this._batteryCb = null; }
    unsubscribeToFlowControlNotifications() { this._flowCb = null; }
    unsubscribeToSensorInterfaceNotifications() { this._sensorCb = null; }
    power(b) { this._sendRaw([0xFF, 0x00, 0x01, b ? 1 : 0, 0xAA]); }
    clear() { this._sendRaw([0xFF, 0x01, 0x00, 0xAA]); }
    grey(g) { this._sendRaw([0xFF, 0x02, 0x01, g & 0x0F, 0xAA]); }
    battery(cb) { if (cb && cb.accept) cb.accept(88); }
    vers(cb) {
        if (cb && cb.accept) cb.accept({
            getMajor: function() { return 4; },
            getMinor: function() { return 2; },
            getPatch: function() { return 0; }
        });
    }
    led(s) {}
    shift(x, y) {
        this._sendRaw([0xFF, 0x09, 0x04, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, 0xAA]);
    }
    settings(cb) {
        if (cb && cb.accept) cb.accept({
            getGlobalXShift: function() { return 0; },
            getGlobalYShift: function() { return 0; },
            getLuma: function() { return 10; },
            isAlsEnable: function() { return true; },
            isGestureEnable: function() { return true; }
        });
    }
    luma(l) { this._sendRaw([0xFF, 0x10, 0x01, l & 0x0F, 0xAA]); }
    sensor(b) { this._sendRaw([0xFF, 0x20, 0x01, b ? 1 : 0, 0xAA]); }
    gesture(b) { this._sendRaw([0xFF, 0x21, 0x01, b ? 1 : 0, 0xAA]); }
    als(b) { this._sendRaw([0xFF, 0x22, 0x01, b ? 1 : 0, 0xAA]); }
    color(c) { this._sendRaw([0xFF, 0x30, 0x01, c & 0xFF, 0xAA]); }
    cfgRead(name, cb) {
        if (cb && cb.accept) cb.accept({
            getVersion: function() { return 42; },
            getNb: function() { return 10; },
            getSize: function() { return 1024; }
        });
    }
    cfgWrite(name, version, data) {}
    cfgSet(name) {}
    layout(id) {}
    layoutDisplay(id, str) {
        const enc = new java.lang.String(String(str == null ? "" : str)).getBytes("UTF-8");
        const frame = [0xFF, 0x62, 0, id & 0xFF];
        for (let i = 0; i < enc.length; i++) frame.push(enc[i] & 0xFF);
        frame.push(0xAA);
        this._sendRaw(frame);
    }
    layoutClear(id) { this._sendRaw([0xFF, 0x63, 0x01, id & 0xFF, 0xAA]); }
    layoutSave(params) {
        try {
            const b = params && params.toBytes ? params.toBytes() : null;
            if (!b) { this._log("layoutSave: no toBytes() on " + params); return; }
            const p = [];
            for (let i = 0; i < b.length; i++) p.push(b[i] & 0xFF);
            if (this.outStream && !this._closed) this._write(this._frame(0x60, p));
        } catch (e) { this._log("layoutSave encode failed: " + e); }
    }
    layoutDelete(id) { this._sendRaw([0xFF, 0x61, 0x01, id & 0xFF, 0xAA]); }
    layoutDeleteAll() {}
    layoutList(cb) { if (cb && cb.accept) cb.accept(new java.util.ArrayList()); }
    layoutPosition(id, x, y) { this._sendRaw([0xFF, 0x65, 0x04, id & 0xFF, (x >> 8) & 0xFF, x & 0xFF, y & 0xFF, 0xAA]); }
    layoutDisplayExtended(id, str, x, y) {
        const enc = new java.lang.String(String(str == null ? "" : str)).getBytes("UTF-8");
        const frame = [0xFF, 0x66, 0, id & 0xFF, (x >> 8) & 0xFF, x & 0xFF, y & 0xFF];
        for (let i = 0; i < enc.length; i++) frame.push(enc[i] & 0xFF);
        frame.push(0xAA);
        this._sendRaw(frame);
    }
    triggerFeature(n) { if (!this.outStream || this._closed) return false; this._write(this._frame(0xF0, [n & 0xFF])); return true; }
    page(id) { this._sendRaw([0xFF, 0x83, 0x01, id & 0xFF, 0xAA]); }
    gauge(id, val) { this._sendRaw([0xFF, 0x70, 0x02, id & 0xFF, val & 0xFF, 0xAA]); }
    txt(x, y, rotation, font_id, color, str) {
        const enc = new java.lang.String(String(str == null ? "" : str)).getBytes("UTF-8");
        const frame = [0xFF, 0x37, 0, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, rotation & 0xFF, font_id & 0xFF, color & 0xFF];
        for (let i = 0; i < enc.length; i++) frame.push(enc[i] & 0xFF);
        frame.push(0x00, 0xAA);
        this._sendRaw(frame);
    }
    text(x, y, rotation, font_id, str) { this.txt(x, y, rotation, font_id, 15, str); }
    point(x, y) { this._sendRaw([0xFF, 0x31, 0x04, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, 0xAA]); }
    line(x0, y0, x1, y1) {
        this._sendRaw([0xFF, 0x32, 0x08, (x0 >> 8) & 0xFF, x0 & 0xFF, (y0 >> 8) & 0xFF, y0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF, 0xAA]);
    }
    rect(x0, y0, x1, y1) {
        this._sendRaw([0xFF, 0x33, 0x08, (x0 >> 8) & 0xFF, x0 & 0xFF, (y0 >> 8) & 0xFF, y0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF, 0xAA]);
    }
    rectf(x0, y0, x1, y1) {
        this._sendRaw([0xFF, 0x34, 0x08, (x0 >> 8) & 0xFF, x0 & 0xFF, (y0 >> 8) & 0xFF, y0 & 0xFF, (x1 >> 8) & 0xFF, x1 & 0xFF, (y1 >> 8) & 0xFF, y1 & 0xFF, 0xAA]);
    }
    circ(x, y, r) {
        this._sendRaw([0xFF, 0x35, 0x05, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, r & 0xFF, 0xAA]);
    }
    circf(x, y, r) {
        this._sendRaw([0xFF, 0x36, 0x05, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, r & 0xFF, 0xAA]);
    }
    polyline(pts) {}
    imgList(cb) { if (cb && cb.accept) cb.accept(new java.util.ArrayList()); }
    imgDisplay(id, x, y) {}
    imgDelete(id) {}
    imgDeleteAll() {}
    fontList(cb) { if (cb && cb.accept) cb.accept(new java.util.ArrayList()); }
    fontSelect(id) {}
    fontDelete(id) {}
    fontDeleteAll() {}
    shutdown() { this.disconnect(); }
}
class OpenBridgeVirtualGlasses {
    constructor(logger) {
        this.__logger = logger || function(msg){ console.log("[OpenBridge] " + msg); };
    }
    getNative() { return null; }
    getManufacturer() { return "Engo"; }
    getName() { return "ENGO 2 000001"; }
    getAddress() { return "OB:77:89:00:00:01"; }
    connect(onConnected, onConnectionFail, onDisconnected) {
        const that = this;
        try { that.__logger("[OpenBridgeVirtualGlasses] connect initiating to 127.0.0.1:7789..."); } catch (e) {}
        const socketGlasses = new OpenBridgeSocketGlasses(that.__logger, onDisconnected);
        socketGlasses.connectSocket("127.0.0.1", 7789, function(success) {
            try { that.__logger("[OpenBridgeVirtualGlasses] connect result: " + success); } catch (e) {}
            if (success) {
                let g = null;
                try { g = new Glasses(socketGlasses); }
                catch (e) { try { that.__logger("[OpenBridgeVirtualGlasses] wrapper fallback: " + e); } catch (x) {} g = socketGlasses; }
                socketGlasses._wrapper = g;
                socketGlasses._onConnected = onConnected;
                if (onConnected) onConnected(g);
                setTimeout(function() { OpenBridgeOverlay.install(); }, 400);
            } else {
                if (onConnectionFail) onConnectionFail(that);
            }
        });
    }
}

// ---- OpenBridge overlay: floating "OB" button + F01-F38 panel (sends 0xF0 <n> to HUD Studio) ----
const OB_FEATURES = [
    ["F01", "Spatial Device Radar", "home"],
    ["F02", "Eyes-On-Target Receipt", "home"],
    ["F03", "Two-Phase Abort Gate", "home"],
    ["F04", "Peripheral Telemetry", "home"],
    ["F05", "Workshop Prompter", "pro"],
    ["F06", "Doorbell Subtitles", "home"],
    ["F07", "AR Compass Wayfinder", "sport"],
    ["F08", "Intrusion Shield", "safety"],
    ["F09", "Bio-Adaptive Pacer", "sport"],
    ["F10", "Touchless Media Remote", "home"],
    ["F11", "TempleTap Morse Input", "ai"],
    ["F12", "Speech Teleprompter", "pro"],
    ["F13", "Energy Ghost Heatmap", "home"],
    ["F14", "Vector Runner Arcade", "sport"],
    ["F15", "Collision Sentry", "safety"],
    ["F16", "Executive Dossier", "pro"],
    ["F17", "Biofeedback Stress", "sport"],
    ["F18", "AR Stud & Inclinometer", "pro"],
    ["F19", "CPR & Triage Pacer", "safety"],
    ["F20", "Directional Subtitles", "ai"],
    ["F21", "UAV Avionics VLOS", "pro"],
    ["F22", "Stealth RF Sentry", "safety"],
    ["F23", "Thermal Arc-Flash", "pro"],
    ["F24", "Allergen Scanner", "safety"],
    ["F25", "Tactical Marine HUD", "sport"],
    ["F26", "Etiquette Whisperer", "ai"],
    ["F27", "Driver Vigilance", "safety"],
    ["F28", "Pick-by-Vision", "pro"],
    ["F29", "Avalanche SAR 457kHz", "safety"],
    ["F30", "Circadian Chrono", "sport"],
    ["F31", "Firefighter Mayday", "safety"],
    ["F32", "Precision Ballistics", "pro"],
    ["F33", "Sterile Surgical HUD", "pro"],
    ["F34", "Low-Vision Echo-Radar", "safety"],
    ["F35", "Neural Voice Co-Pilot", "ai"],
    ["F36", "Multimodal Vision Proxy", "ai"],
    ["F37", "Ambient IoT Matrix", "home"],
    ["F38", "Spatial Translation", "ai"]
];
const OB_CATS = {
    home: ["Home & IoT", "#22D3EE"],
    sport: ["Sport & Bio", "#A3E635"],
    pro: ["Pro & Industry", "#F59E0B"],
    safety: ["Safety-critical", "#F43F5E"],
    ai: ["Neural & AI", "#A78BFA"]
};
const OpenBridgeOverlay = {
    _fab: null, _act: null, _tour: null, _dialog: null,
    activity() {
        try { if (typeof d !== "undefined" && d && d.yA) return d.yA.foregroundActivity || d.yA.startActivity; } catch (e) {}
        return null;
    },
    dp(act, v) { return Math.round(v * act.getResources().getDisplayMetrics().density); },
    install() {
        const act = this.activity();
        if (!act) { console.log("[OpenBridge] overlay: no activity yet"); return; }
        if (this._fab && this._act === act) return;
        this._act = act;
        try { this._buildFab(act); console.log("[OpenBridge] overlay installed"); }
        catch (e) { console.log("[OpenBridge] overlay failed: " + e); }
    },
    _round(color, radius, stroke, strokeColor) {
        const C = android.graphics.Color;
        const g = new android.graphics.drawable.GradientDrawable();
        g.setColor(C.parseColor(color));
        if (radius < 0) g.setShape(android.graphics.drawable.GradientDrawable.OVAL); else g.setCornerRadius(radius);
        if (stroke) g.setStroke(stroke, C.parseColor(strokeColor));
        return g;
    },
    _text(act, txt, sizeSp, color, bold, mono) {
        const t = new android.widget.TextView(act);
        t.setText(txt); t.setTextSize(sizeSp); t.setTextColor(android.graphics.Color.parseColor(color));
        if (mono) t.setTypeface(android.graphics.Typeface.MONOSPACE, bold ? 1 : 0);
        else if (bold) t.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        return t;
    },
    _buildFab(act) {
        const self = this, G = android.view.Gravity, dp = function(v) { return self.dp(act, v); };
        const fab = this._text(act, "OB", 15, "#0A0D12", true, false);
        fab.setGravity(G.CENTER);
        fab.setBackground(this._round("#E4F222", -1, dp(3), "#0A0D12"));
        fab.setElevation(dp(12));
        const lp = new android.widget.FrameLayout.LayoutParams(dp(58), dp(58), G.BOTTOM | G.END);
        lp.setMargins(0, 0, dp(16), dp(128));
        const st = { x0: 0, y0: 0, dx: 0, dy: 0, moved: false };
        fab.setOnTouchListener(new android.view.View.OnTouchListener({
            onTouch: function(v, ev) {
                const a = ev.getActionMasked();
                if (a === 0) { st.x0 = ev.getRawX(); st.y0 = ev.getRawY(); st.dx = v.getX() - st.x0; st.dy = v.getY() - st.y0; st.moved = false; return true; }
                if (a === 2) {
                    if (Math.abs(ev.getRawX() - st.x0) + Math.abs(ev.getRawY() - st.y0) > dp(10)) st.moved = true;
                    if (st.moved) { v.setX(ev.getRawX() + st.dx); v.setY(ev.getRawY() + st.dy); }
                    return true;
                }
                if (a === 1) { if (!st.moved) self.openPanel(); return true; }
                return false;
            }
        }));
        act.getWindow().getDecorView().addView(fab, lp);
        this._fab = fab;
    },
    connected() { const g = global.OpenBridgeActiveGlasses; return !!(g && g.outStream && !g._closed); },
    toast(msg) { try { android.widget.Toast.makeText(this._act, msg, 0).show(); } catch (e) {} },
    trigger(n) {
        const g = global.OpenBridgeActiveGlasses;
        if (!this.connected()) { this.toast("HUD Studio not connected"); return false; }
        g.triggerFeature(n);
        const f = OB_FEATURES[n - 1];
        this.toast((f ? f[0] + " · " + f[1] : "F" + n) + "  →  HUD");
        return true;
    },
    pill(act, label, bg, fg, onClick) {
        const self = this, dp = function(v) { return self.dp(act, v); };
        const b = this._text(act, label, 13, fg, true, false);
        b.setPadding(dp(14), dp(9), dp(14), dp(9));
        b.setBackground(this._round(bg, dp(18), 0, null));
        b.setOnClickListener(new android.view.View.OnClickListener({ onClick: function() { onClick(); } }));
        const lp = new android.widget.LinearLayout.LayoutParams(-2, -2);
        lp.setMargins(0, 0, dp(8), 0);
        b.setLayoutParams(lp);
        return b;
    },
    openPanel() {
        const act = this._act || this.activity();
        if (!act) return;
        const self = this, dp = function(v) { return self.dp(act, v); }, C = android.graphics.Color;
        const root = new android.widget.LinearLayout(act);
        root.setOrientation(1);
        root.setPadding(dp(20), dp(18), dp(20), dp(12));
        root.setBackground(this._round("#0D1117", dp(24), dp(1), "#1F2935"));
        root.addView(this._text(act, "OpenBridge HUD", 22, "#DCE3EC", true, false));
        const on = this.connected();
        const sub = this._text(act, (on ? "●  Connected to HUD Studio" : "○  HUD Studio not connected") + "   ·   38 features", 12, on ? "#34D399" : "#F59E0B", false, false);
        sub.setPadding(0, dp(2), 0, dp(12));
        root.addView(sub);
        const actions = new android.widget.LinearLayout(act);
        actions.setOrientation(0);
        actions.addView(this.pill(act, "👋 Wave", "#E4F222", "#0A0D12", function() {
            const g = global.OpenBridgeActiveGlasses; if (g) g._fireGesture(); self.toast("Wave sent to the app");
        }));
        actions.addView(this.pill(act, "⌫ Clear", "#18202B", "#DCE3EC", function() {
            const g = global.OpenBridgeActiveGlasses; if (g && self.connected()) g.clear();
        }));
        const tourBtn = this.pill(act, this._tour ? "■ Stop tour" : "▶ Tour", "#18202B", "#DCE3EC", function() { self.toggleTour(tourBtn); });
        actions.addView(tourBtn);
        root.addView(actions);
        const scroll = new android.widget.ScrollView(act);
        const list = new android.widget.LinearLayout(act);
        list.setOrientation(1);
        list.setPadding(0, dp(10), 0, dp(6));
        let lastCat = null;
        const order = Object.keys(OB_CATS);
        const sorted = OB_FEATURES.map(function(f, i) { return [f, i + 1]; })
            .sort(function(a, b) { return (order.indexOf(a[0][2]) - order.indexOf(b[0][2])) || (a[1] - b[1]); });
        for (let k = 0; k < sorted.length; k++) {
            const f = sorted[k][0], cat = OB_CATS[f[2]], n = sorted[k][1];
            if (f[2] !== lastCat) {
                lastCat = f[2];
                const count = OB_FEATURES.filter(function(x) { return x[2] === f[2]; }).length;
                const h = this._text(act, cat[0].toUpperCase() + "   \u00B7   " + count, 11, cat[1], true, false);
                h.setPadding(dp(2), dp(14), 0, dp(6));
                list.addView(h);
            }
            const row = new android.widget.LinearLayout(act);
            row.setOrientation(0);
            row.setGravity(android.view.Gravity.CENTER_VERTICAL);
            row.setPadding(dp(12), dp(11), dp(12), dp(11));
            row.setBackground(this._round("#121822", dp(12), 0, null));
            const rlp = new android.widget.LinearLayout.LayoutParams(-1, -2);
            rlp.setMargins(0, 0, 0, dp(6));
            row.setLayoutParams(rlp);
            const bar = new android.view.View(act);
            bar.setBackground(this._round(cat[1], dp(2), 0, null));
            row.addView(bar, new android.widget.LinearLayout.LayoutParams(dp(4), dp(26)));
            const id = this._text(act, f[0], 13, "#8592A3", true, true);
            id.setPadding(dp(12), 0, dp(12), 0);
            row.addView(id);
            row.addView(this._text(act, f[1], 15, "#DCE3EC", false, false));
            row.setOnClickListener(new android.view.View.OnClickListener({ onClick: function() { self.trigger(n); } }));
            list.addView(row);
        }
        scroll.addView(list);
        root.addView(scroll, new android.widget.LinearLayout.LayoutParams(-1, 0, 1.0));
        const close = this._text(act, "Close", 14, "#8592A3", true, false);
        close.setGravity(android.view.Gravity.CENTER);
        close.setPadding(0, dp(12), 0, dp(4));
        root.addView(close);
        const dlg = new android.app.AlertDialog.Builder(act).setView(root).create();
        close.setOnClickListener(new android.view.View.OnClickListener({ onClick: function() { dlg.dismiss(); } }));
        dlg.show();
        const w = dlg.getWindow();
        w.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(C.TRANSPARENT));
        const dm = act.getResources().getDisplayMetrics();
        w.setLayout(Math.round(dm.widthPixels * 0.92), Math.round(dm.heightPixels * 0.82));
        this._dialog = dlg;
    },
    toggleTour(btn) {
        const self = this;
        if (this._tour) { clearInterval(this._tour); this._tour = null; if (btn) btn.setText("▶ Tour"); return; }
        let n = 0;
        const step = function() { n = n % OB_FEATURES.length + 1; if (!self.trigger(n)) { clearInterval(self._tour); self._tour = null; } };
        step();
        this._tour = setInterval(step, 3200);
        if (btn) btn.setText("■ Stop tour");
    }
};
global.OpenBridgeOverlay = OpenBridgeOverlay;
global.OpenBridgeVirtualGlasses = OpenBridgeVirtualGlasses;
global.OpenBridgeSocketGlasses = OpenBridgeSocketGlasses;
// --- OPENBRIDGE EMULATOR BRIDGE END ---
"""

SERIAL_NEEDLE = "connectSerializedGlasses(e,t,a,i){if(!this.sdkProxy)return;"
SERIAL_HOOK = ('connectSerializedGlasses(e,t,a,i){try{if(String(e)==="OB-SERIALIZED-EMULATOR"&&global.OpenBridgeVirtualGlasses)'
               '{new global.OpenBridgeVirtualGlasses(this.__logger).connect(t,a,i);return;}}catch(_e){};if(!this.sdkProxy)return;')


SCAN_HOOK_V1 = "startScan(e){try{if(global.OpenBridgeVirtualGlasses){e(new global.OpenBridgeVirtualGlasses(this.__logger));}}catch(_e){};"
SCAN_HOOK_V2 = ("startScan(e){try{if(global.OpenBridgeVirtualGlasses&&(!global.__obLastScanEmit||Date.now()-global.__obLastScanEmit>4000))"
                "{global.__obLastScanEmit=Date.now();e(new global.OpenBridgeVirtualGlasses(this.__logger));}}catch(_e){};")
SENTRY_NEEDLE = "class CrashReportService extends s.cP{constructor(){super(...arguments);this.sentryEnabled=!0;"
SENTRY_OFF = "class CrashReportService extends s.cP{constructor(){super(...arguments);this.sentryEnabled=!1;"
SENTRY_ENABLE_NEEDLE = "async enable(){this.sentryEnabled=!0;"
SENTRY_ENABLE_OFF = "async enable(){this.sentryEnabled=!1;return;"
# The de-split APK lost res/drawable-xxhdpi/ic_stat_glasses from resources.arsc (density split), so the
# foreground-service notification is rejected ("no valid small icon"). Fall back to a framework icon.
ICON_NEEDLE = 't.setSmallIcon(r.yA.resources.getDrawableId("ic_stat_glasses"));'
ICON_FIX = 't.setSmallIcon(r.yA.resources.getDrawableId("ic_stat_glasses")||android.R.drawable.stat_sys_data_bluetooth);'


def apply_extra_hooks(js: str) -> str:
    """v3: emit the virtual glasses once per scan burst (the app calls startScan twice) and keep
    the dev build fully offline from Sentry (it is already a no-op in this build; make it explicit)."""
    if SCAN_HOOK_V1 in js:
        js = js.replace(SCAN_HOOK_V1, SCAN_HOOK_V2, 1)
        print("[Build] startScan hook upgraded (single emission per scan burst)")
    elif SCAN_HOOK_V2 not in js:
        raise RuntimeError("startScan hook not found")
    for needle, repl, label in ((SENTRY_NEEDLE, SENTRY_OFF, "constructor"), (SENTRY_ENABLE_NEEDLE, SENTRY_ENABLE_OFF, "enable()"),
                                (ICON_NEEDLE, ICON_FIX, "notification small icon fallback")):
        if repl in js:
            continue
        if js.count(needle) != 1:
            raise RuntimeError(f"Sentry {label} needle count != 1")
        js = js.replace(needle, repl, 1)
        print(f"[Build] patched: {label}")
    return js


def apply_serialized_hook(js: str) -> str:
    """Route the saved emulator 'serialized glasses' back to the virtual device on app restart
    (otherwise the real SDK receives a plain String and the auto-reconnect fails)."""
    if SERIAL_HOOK in js:
        return js
    if SERIAL_NEEDLE not in js:
        raise RuntimeError("connectSerializedGlasses needle not found in bundle.js")
    print("[Build] Injected OB-SERIALIZED-EMULATOR reconnect hook")
    return js.replace(SERIAL_NEEDLE, SERIAL_HOOK, 1)


def main():
    base_apk = PROJECT_ROOT / "activelook_base.apk"
    if not base_apk.exists():
        raise RuntimeError(f"Base APK not found at {base_apk}")

    print("[Build] Reading bundle.js from base APK...")
    with zipfile.ZipFile(base_apk, "r") as z:
        js = z.read("assets/app/bundle.js").decode("utf-8", errors="replace")

    # Inject OpenBridge classes before class GlassesSDK
    idx = js.find("class GlassesSDK{")
    if idx == -1:
        raise RuntimeError("class GlassesSDK not found in bundle.js")

    js_patched = js[:idx] + PATCH_JS + "\n" + js[idx:]

    # Inject into startScan(e)
    scan_needle = "startScan(e){if(!this.sdkProxy)return;const t=this;this.sdkProxy.startScan(new u({accept(a){"
    scan_idx = js_patched.find(scan_needle)
    if scan_idx != -1:
        scan_inject = "startScan(e){try{if(global.OpenBridgeVirtualGlasses){e(new global.OpenBridgeVirtualGlasses(this.__logger));}}catch(_e){};"
        js_patched = js_patched[:scan_idx] + scan_inject + js_patched[scan_idx + len("startScan(e){"):]
        print("[Build] Successfully injected OpenBridgeVirtualGlasses into startScan!")
    else:
        raise RuntimeError("startScan needle not matched exactly in bundle.js")

    js_patched = apply_serialized_hook(js_patched)
    js_patched = apply_extra_hooks(js_patched)

    out_base_unaligned = PROJECT_ROOT / "activelook_patched_unaligned.apk"
    out_base_aligned = PROJECT_ROOT / "activelook_patched_aligned.apk"
    out_base_signed = PROJECT_ROOT / "activelook_openbridge_base.apk"

    print("[Build] Writing patched APK...")
    with zipfile.ZipFile(base_apk, "r") as zin, zipfile.ZipFile(out_base_unaligned, "w") as zout:
        for item in zin.infolist():
            # Skip old signatures
            if item.filename.startswith("META-INF/BNDLTOOL") or item.filename == "META-INF/MANIFEST.MF":
                continue
            if item.filename == "assets/app/bundle.js":
                zout.writestr(item, js_patched.encode("utf-8"))
            else:
                zout.writestr(item, zin.read(item.filename))

    print("[Build] Running zipalign...")
    zipalign_bin = SDK / "zipalign.exe"
    subprocess.run([str(zipalign_bin), "-f", "-p", "4", str(out_base_unaligned), str(out_base_aligned)], check=True)

    print("[Build] Signing base APK with OpenBridge keystore...")
    apksigner_bin = SDK / "apksigner.bat"
    subprocess.run([
        str(apksigner_bin), "sign",
        "--ks", str(KEYSTORE),
        "--ks-pass", f"pass:{PW}",
        "--out", str(out_base_signed),
        str(out_base_aligned)
    ], check=True, shell=True)

    # Sign split APKs as well
    split_arm = PROJECT_ROOT / "split_config.arm64_v8a.apk"
    signed_arm = PROJECT_ROOT / "activelook_openbridge_arm64.apk"
    subprocess.run([
        str(apksigner_bin), "sign",
        "--ks", str(KEYSTORE),
        "--ks-pass", f"pass:{PW}",
        "--out", str(signed_arm),
        str(split_arm)
    ], check=True, shell=True)

    split_fr = PROJECT_ROOT / "split_config.fr.apk"
    signed_fr = PROJECT_ROOT / "activelook_openbridge_fr.apk"
    subprocess.run([
        str(apksigner_bin), "sign",
        "--ks", str(KEYSTORE),
        "--ks-pass", f"pass:{PW}",
        "--out", str(signed_fr),
        str(split_fr)
    ], check=True, shell=True)

    split_dpi = PROJECT_ROOT / "split_config.xxhdpi.apk"
    signed_dpi = PROJECT_ROOT / "activelook_openbridge_xxhdpi.apk"
    subprocess.run([
        str(apksigner_bin), "sign",
        "--ks", str(KEYSTORE),
        "--ks-pass", f"pass:{PW}",
        "--out", str(signed_dpi),
        str(split_dpi)
    ], check=True, shell=True)

    print("[Build] Verifying signatures...")
    subprocess.run([str(apksigner_bin), "verify", str(out_base_signed)], check=True, shell=True)
    subprocess.run([str(apksigner_bin), "verify", str(signed_arm)], check=True, shell=True)

    print("[Build] SUCCESS! Generated signed ActiveLook OpenBridge APKs:")
    print(" - Base:", out_base_signed)
    print(" - ARM64:", signed_arm)
    print(" - FR:", signed_fr)
    print(" - XXHDPI:", signed_dpi)

if __name__ == "__main__":
    main()
