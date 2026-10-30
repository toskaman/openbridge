package fr.openbridge.companion;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.graphics.PorterDuffXfermode;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.View;
import java.util.ArrayDeque;
import java.util.Random;

/**
 * Full-screen, touch-transparent layer above the companion UI that shows live data flows:
 * every message this device sends leaves the voice orb as an amber comet and flies off-screen,
 * every message received flies in from outside as an emerald comet and dives into the orb.
 * Each comet carries a short label (operation + size). Same language as the PC agents.
 *
 * {@link #flow} is thread-safe (the relay calls it from its own thread). Nothing is drawn and no
 * frame is scheduled while there are no comets, so an idle screen costs nothing.
 */
public class FlowOverlayView extends View {
    public static final int IN = 0, OUT = 1;
    private static final int MAX = 48, TRAIL = 16;
    public static final int C_OUT = Color.rgb(255, 176, 64), C_IN = Color.rgb(52, 255, 170);

    private static final class Comet {
        boolean alive, labeled; int dir; float t, life, size, ax, ay, bx, by, cx, cy; int tn; String label;
        final float[] tx = new float[TRAIL], ty = new float[TRAIL];
        final RectF pill = new RectF(); boolean pillOn; float pillA;
    }
    private static final class Event { int dir; String label; long bytes; }

    private final Comet[] comets = new Comet[MAX];
    private final ArrayDeque<Event> queue = new ArrayDeque<>();
    private final Random rnd = new Random();
    private View anchor;
    private volatile boolean show = true;
    private final long[] msgs = new long[2];
    private final double[] rate = new double[2], acc = new double[2];
    private final float[] act = new float[2];
    private final long[] lastLabelAt = new long[2];
    private final String[] lastLabel = {"", ""};
    private long rateAt, lastNs;
    private final int[] loc = new int[2], aloc = new int[2];
    private final Paint glow = new Paint(Paint.ANTI_ALIAS_FLAG), pillFill = new Paint(Paint.ANTI_ALIAS_FLAG),
            pillLine = new Paint(Paint.ANTI_ALIAS_FLAG), label = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float dp;

    public FlowOverlayView(Context c) {
        super(c);
        dp = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, 1, c.getResources().getDisplayMetrics());
        for (int i = 0; i < MAX; i++) comets[i] = new Comet();
        glow.setXfermode(new PorterDuffXfermode(PorterDuff.Mode.ADD));
        pillFill.setColor(Color.argb(205, 9, 12, 24));
        pillLine.setStyle(Paint.Style.STROKE); pillLine.setStrokeWidth(dp);
        label.setTextSize(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 11, c.getResources().getDisplayMetrics()));
        label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        setClickable(false); setFocusable(false);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }

    /** The view the comets leave from / dive into (the voice orb). */
    public void setAnchor(View v) { anchor = v; }
    public void setShowFlows(boolean on) {
        show = on;
        if (!on) post(() -> { for (Comet c : comets) c.alive = false; invalidate(); });
    }
    public boolean showFlows() { return show; }
    public synchronized long messages(int dir) { return msgs[dir]; }
    public synchronized double bytesPerSecond(int dir) { return rate[dir]; }
    public float activity(int dir) { return act[dir]; }

    /** One message crossed the link. Any thread. */
    public void flow(int dir, String what, long bytes) {
        Event e = new Event(); e.dir = dir == OUT ? OUT : IN; e.label = what == null ? "?" : what; e.bytes = Math.max(0, bytes);
        synchronized (queue) { if (queue.size() < 256) queue.add(e); }
        postInvalidateOnAnimation();
    }

    static String human(long n) {
        if (n < 1024) return n + " B";
        double v = n / 1024.0; String u = "KB";
        if (v >= 1024) { v /= 1024; u = "MB"; }
        return (v < 10 ? String.format(java.util.Locale.US, "%.1f", v) : String.valueOf(Math.round(v))) + " " + u;
    }

    private float orbX, orbY, orbR;
    private boolean locateOrb() {
        if (anchor == null || anchor.getWidth() <= 0 || anchor.getHeight() <= 0) return false;
        anchor.getLocationInWindow(aloc); getLocationInWindow(loc);
        orbX = aloc[0] - loc[0] + anchor.getWidth() / 2f;
        orbY = aloc[1] - loc[1] + anchor.getHeight() / 2f;
        orbR = Math.min(anchor.getWidth(), anchor.getHeight()) * 0.30f;
        return orbR >= 1f;
    }

    private void spawn(Event e, int[] budget) {
        synchronized (this) { msgs[e.dir]++; acc[e.dir] += e.bytes; }
        act[e.dir] = Math.min(1f, act[e.dir] + 0.35f);
        if (anchor instanceof VoiceOrbView) ((VoiceOrbView) anchor).bump(e.dir == OUT ? 0.30f : 0.20f);
        if (!show || budget[e.dir] <= 0 || getWidth() <= 0) return;
        budget[e.dir]--;
        Comet c = null; int labeled = 0;
        for (Comet k : comets) { if (k.alive && k.labeled) labeled++; if (c == null && !k.alive) c = k; }
        if (c == null) return;
        float ang = rnd.nextFloat() * 6.2831853f, ux = (float) Math.cos(ang), uy = (float) Math.sin(ang);
        float reach = (float) Math.hypot(getWidth(), getHeight()) * 0.8f + 60 * dp;
        float sx = orbX + ux * orbR * 0.98f, sy = orbY + uy * orbR * 0.98f, ox = orbX + ux * reach, oy = orbY + uy * reach;
        if (e.dir == OUT) { c.ax = sx; c.ay = sy; c.bx = ox; c.by = oy; } else { c.ax = ox; c.ay = oy; c.bx = sx; c.by = sy; }
        float dx = c.bx - c.ax, dy = c.by - c.ay, L = (float) Math.hypot(dx, dy) + 1e-3f;
        float bend = (0.10f + 0.16f * rnd.nextFloat()) * L * (e.dir == OUT ? 1f : -1f);
        c.cx = (c.ax + c.bx) / 2f - dy / L * bend; c.cy = (c.ay + c.by) / 2f + dx / L * bend;
        c.life = (e.dir == OUT ? 1.45f : 1.65f) + rnd.nextFloat() * 0.55f;
        c.dir = e.dir; c.t = 0; c.tn = 0; c.alive = true; c.pillOn = false;
        long now = System.currentTimeMillis();
        boolean fresh = !e.label.equals(lastLabel[e.dir]) || now - lastLabelAt[e.dir] > 650;
        c.labeled = fresh && labeled < 8;
        c.size = (c.labeled ? 3.0f : 1.9f) * dp + (float) Math.min(2.2, Math.log10(e.bytes + 1.0) * 0.32) * dp;
        if (c.labeled) {
            String name = e.label.length() > 26 ? e.label.substring(0, 25) + "…" : e.label;
            c.label = (e.dir == OUT ? "↑ " : "↓ ") + name + (e.bytes > 0 ? "  ·  " + human(e.bytes) : "");
            lastLabel[e.dir] = e.label; lastLabelAt[e.dir] = now;
        }
    }

    private static float clamp(float v, float a, float b) { return v < a ? a : v > b ? b : v; }
    private float fade(Comet c) {
        if (c.dir == OUT) return clamp(c.t / 0.06f, 0, 1) * clamp((1 - c.t) / 0.18f, 0, 1);
        return clamp(c.t / 0.12f, 0, 1) * clamp((1 - c.t) / 0.06f, 0, 1);
    }
    private void glowCircle(Canvas cv, float x, float y, float r, int rgb, float a) {
        if (a <= 0.004f || !(r > 0.1f)) return;
        glow.setColor(Color.argb(Math.min(255, Math.round(a * 255)), Color.red(rgb), Color.green(rgb), Color.blue(rgb)));
        cv.drawCircle(x, y, r, glow);
    }

    @Override protected void onDraw(Canvas cv) {
        long ns = System.nanoTime();
        float dt = lastNs == 0 ? 0.016f : Math.min(0.1f, (ns - lastNs) / 1e9f);
        lastNs = ns;
        boolean located = locateOrb();

        int[] budget = {4, 4};
        while (true) {
            Event e; synchronized (queue) { e = queue.poll(); }
            if (e == null) break;
            if (located) spawn(e, budget);
            else { synchronized (this) { msgs[e.dir]++; acc[e.dir] += e.bytes; } }
        }
        long now = System.currentTimeMillis();
        if (rateAt == 0) rateAt = now;
        if (now - rateAt >= 500) {
            double k = 1000.0 / (now - rateAt);
            synchronized (this) { for (int d = 0; d < 2; d++) { rate[d] = rate[d] * 0.4 + acc[d] * k * 0.6; acc[d] = 0; } }
            rateAt = now;
        }
        for (int d = 0; d < 2; d++) act[d] *= (float) Math.pow(0.25, dt);

        boolean any = false;
        for (Comet c : comets) {
            if (!c.alive) continue;
            c.t += dt / c.life;
            if (c.t >= 1f) { if (c.dir == IN && anchor instanceof VoiceOrbView) ((VoiceOrbView) anchor).bump(0.45f); c.alive = false; continue; }
            any = true;
            float u = c.dir == OUT ? (float) Math.pow(c.t, 1.6) : 1f - (float) Math.pow(1f - c.t, 1.7);
            float a = (1 - u) * (1 - u), b = 2 * (1 - u) * u, d = u * u;
            float x = a * c.ax + b * c.cx + d * c.bx, y = a * c.ay + b * c.cy + d * c.by;
            int n = Math.min(TRAIL, c.tn + 1);
            for (int k = n - 1; k > 0; k--) { c.tx[k] = c.tx[k - 1]; c.ty[k] = c.ty[k - 1]; }
            c.tx[0] = x; c.ty[0] = y; c.tn = n;

            int col = c.dir == OUT ? C_OUT : C_IN;
            int hot = Color.rgb(Color.red(col) + (255 - Color.red(col)) * 65 / 100, Color.green(col) + (255 - Color.green(col)) * 65 / 100,
                    Color.blue(col) + (255 - Color.blue(col)) * 65 / 100);
            float f0 = fade(c), shrink = c.dir == IN ? clamp((1 - c.t) / 0.25f, 0.35f, 1f) : 1f;
            for (int k = c.tn - 1; k >= 1; k--) {                    /* continuous trail */
                float x0 = c.tx[k], y0 = c.ty[k], x1 = c.tx[k - 1], y1 = c.ty[k - 1];
                int steps = Math.min(36, (int) (Math.hypot(x1 - x0, y1 - y0) / (2.2f * dp)) + 1);
                for (int j = 0; j < steps; j++) {
                    float uu = (float) j / steps, f = 1f - (k - uu) / TRAIL;
                    glowCircle(cv, x0 + (x1 - x0) * uu, y0 + (y1 - y0) * uu, c.size * shrink * (0.22f + 0.55f * f), col, 0.22f * f * f * f0);
                }
            }
            glowCircle(cv, x, y, c.size * 3.2f * shrink, col, 0.10f * f0);
            glowCircle(cv, x, y, c.size * 1.7f * shrink, col, 0.32f * f0);
            glowCircle(cv, x, y, c.size * 0.9f * shrink, hot, 0.95f * f0);
        }

        /* labels: beside the comet, never on the orb, never on each other */
        for (int i = 0; i < MAX; i++) {
            Comet c = comets[i];
            c.pillOn = false;
            if (!c.alive || !c.labeled || c.tn < 2) continue;
            float al = fade(c) * (c.dir == IN ? clamp((1 - c.t) / 0.3f, 0, 1) : clamp((1 - c.t) / 0.45f, 0, 1));
            if (al < 0.05f) continue;
            float hx = c.tx[0], hy = c.ty[0];
            if (located && Math.hypot(hx - orbX, hy - orbY) < orbR * 1.45f) continue;
            float vx = c.tx[0] - c.tx[1], vy = c.ty[0] - c.ty[1], L = (float) Math.hypot(vx, vy) + 1e-3f;
            float nx = -vy / L, ny = vx / L;
            float w = label.measureText(c.label) + 16 * dp, h = 20 * dp;
            float px = hx + nx * 14 * dp - (nx < 0 ? w : 0), py = hy + ny * 14 * dp - h / 2;
            if (px < 4 * dp || py < 26 * dp || px + w > getWidth() - 4 * dp || py + h > getHeight() - 4 * dp) continue;
            c.pill.set(px, py, px + w, py + h);
            if (located) {                                      /* the whole label stays off the sphere, not just the comet head */
                float qx = Math.max(c.pill.left, Math.min(orbX, c.pill.right)), qy = Math.max(c.pill.top, Math.min(orbY, c.pill.bottom));
                if (Math.hypot(qx - orbX, qy - orbY) < orbR * 1.3f) continue;
            }
            boolean clash = false;
            for (int j = 0; j < i && !clash; j++) if (comets[j].pillOn && RectF.intersects(comets[j].pill, c.pill)) clash = true;
            if (clash) continue;
            c.pillOn = true;
            int col = c.dir == OUT ? C_OUT : C_IN;
            pillFill.setAlpha(Math.round(205 * al));
            cv.drawRoundRect(c.pill, h / 2, h / 2, pillFill);
            pillLine.setColor(Color.argb(Math.round(180 * al), Color.red(col), Color.green(col), Color.blue(col)));
            cv.drawRoundRect(c.pill, h / 2, h / 2, pillLine);
            label.setColor(Color.argb(Math.round(255 * al), Math.min(255, Color.red(col) + 60), Math.min(255, Color.green(col) + 40), Math.min(255, Color.blue(col) + 40)));
            Paint.FontMetrics fm = label.getFontMetrics();
            cv.drawText(c.label, px + 8 * dp, py + h / 2 - (fm.ascent + fm.descent) / 2, label);
        }
        boolean pending; synchronized (queue) { pending = !queue.isEmpty(); }
        if ((any || pending || act[0] > 0.02f || act[1] > 0.02f) && isAttachedToWindow()) postInvalidateOnAnimation();
        else lastNs = 0;
    }
}
