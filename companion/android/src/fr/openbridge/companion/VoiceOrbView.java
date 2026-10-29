package fr.openbridge.companion;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PorterDuff;
import android.graphics.PorterDuffXfermode;
import android.graphics.LinearGradient;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.util.TypedValue;
import android.view.View;

/**
 * Futuristic "voice" presence: a 3D particle sphere that breathes, ripples and spins, with luminous
 * Siri-style ribbons through its equator. Pure Canvas, no libraries, no bitmaps.
 *
 * Inputs (all thread-safe): {@link #setState(int)}, {@link #setLevel(float)} (live mic / speech level 0..1),
 * {@link #pulse()} (something happened) and {@link #bump(float)} (a short burst, e.g. a spoken word).
 */
public class VoiceOrbView extends View {
    public static final int IDLE = 0, LISTENING = 1, THINKING = 2, SPEAKING = 3, ALERT = 4, OFFLINE = 5;

    /** Three colour stops per state: primary, secondary, highlight. */
    private static final int[][] PALETTE = {
            {Color.rgb(64, 196, 255), Color.rgb(124, 77, 255), Color.rgb(0, 229, 255)},     // idle: cyan / violet
            {Color.rgb(0, 229, 255), Color.rgb(41, 121, 255), Color.rgb(29, 233, 182)},     // listening: cyan / blue / mint
            {Color.rgb(179, 136, 255), Color.rgb(101, 31, 255), Color.rgb(0, 176, 255)},    // thinking: violet swirl
            {Color.rgb(255, 79, 216), Color.rgb(140, 91, 255), Color.rgb(255, 158, 94)},    // speaking: magenta / violet / amber
            {Color.rgb(255, 183, 77), Color.rgb(255, 110, 64), Color.rgb(255, 213, 79)},    // alert: amber
            {Color.rgb(96, 110, 140), Color.rgb(70, 78, 110), Color.rgb(120, 140, 170)},    // offline: dim steel
    };

    private static final int LAT = 18, LON = 46;
    private final float[] ux = new float[LAT * LON], uy = new float[LAT * LON], uz = new float[LAT * LON];
    private final float[] lat01 = new float[LAT * LON], lon01 = new float[LAT * LON], poleW = new float[LAT * LON];

    private volatile int state = IDLE;
    private volatile float input;        // last external level 0..1 (decays)
    private volatile float burst;        // short bursts (words, key presses)
    private volatile long pulseAt;       // last event time (ns)

    private final float[][] col = new float[3][3];   // current colours (lerped toward the state palette)
    private float level, energy, spin, think, speakMix, listenMix;
    private float t;
    private long lastNs;

    private final Paint dot = new Paint(Paint.ANTI_ALIAS_FLAG), fill = new Paint(Paint.ANTI_ALIAS_FLAG),
            stroke = new Paint(Paint.ANTI_ALIAS_FLAG), glow = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF arc = new RectF();
    private final float density;

    public VoiceOrbView(Context c) {
        super(c);
        density = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, 1, c.getResources().getDisplayMetrics());
        PorterDuffXfermode add = new PorterDuffXfermode(PorterDuff.Mode.ADD);
        dot.setXfermode(add); fill.setXfermode(add); stroke.setXfermode(add); glow.setXfermode(add);
        fill.setStyle(Paint.Style.FILL);
        stroke.setStyle(Paint.Style.STROKE); stroke.setStrokeCap(Paint.Cap.ROUND);
        int i = 0;
        for (int a = 0; a < LAT; a++) {
            double th = Math.PI * (a + 0.5) / LAT;
            for (int b = 0; b < LON; b++, i++) {
                double ph = 2 * Math.PI * (b + (a % 2) * 0.5) / LON;
                ux[i] = (float) (Math.sin(th) * Math.cos(ph));
                uy[i] = (float) Math.cos(th);
                uz[i] = (float) (Math.sin(th) * Math.sin(ph));
                lat01[i] = (float) a / LAT; lon01[i] = (float) b / LON;
                poleW[i] = (float) Math.pow(Math.sin(th), 1.5);   // calmer poles: no loops where meridians converge
            }
        }
        for (int k = 0; k < 3; k++) setRgb(col[k], PALETTE[IDLE][k]);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }

    public void setState(int s) { if (s != state) { state = s; pulseAt = System.nanoTime(); } }
    public int state() { return state; }
    /** Live amplitude 0..1 (mic RMS, speech envelope). Call as often as you like from any thread. */
    public void setLevel(float l) { input = Math.max(0f, Math.min(1f, l)); }
    /** Something happened: a ring ripples out and the sphere flares. */
    public void pulse() { pulseAt = System.nanoTime(); burst = Math.max(burst, 0.6f); }
    /** Short burst of motion (a spoken word, a typed key). */
    public void bump(float b) { burst = Math.max(burst, Math.min(1f, b)); }

    @Override protected void onAttachedToWindow() { super.onAttachedToWindow(); lastNs = 0; postInvalidateOnAnimation(); }

    @Override protected void onDraw(Canvas c) {
        long now = System.nanoTime();
        float dt = lastNs == 0 ? 0.016f : Math.min(0.05f, (now - lastNs) / 1e9f);
        lastNs = now; t += dt;
        int s = state;

        // ---- dynamics -------------------------------------------------------------------------------
        float in = input; input = in * (float) Math.pow(0.25, dt);           // external level fades if not refreshed
        float b = burst; burst = b * (float) Math.pow(0.04, dt);
        float synth = 0f;
        if (s == SPEAKING) synth = 0.28f + 0.30f * Math.abs((float) (Math.sin(t * 8.7) * Math.sin(t * 3.1 + 1)));
        else if (s == THINKING) synth = 0.18f + 0.08f * (float) Math.sin(t * 2.4);
        else if (s == IDLE || s == OFFLINE) synth = 0.04f + 0.03f * (float) Math.sin(t * 1.1);
        else if (s == ALERT) synth = 0.25f + 0.15f * (float) Math.sin(t * 4);
        float target = Math.min(1f, Math.max(in, synth) + b * 0.6f);
        level += (target - level) * Math.min(1f, dt * (target > level ? 14f : 5f));
        float base = s == OFFLINE ? 0.05f : s == IDLE ? 0.12f : s == THINKING ? 0.45f : 0.3f;
        energy += (base + level * 0.7f - energy) * Math.min(1f, dt * 4f);
        think += ((s == THINKING ? 1f : 0f) - think) * Math.min(1f, dt * 3f);
        speakMix += ((s == SPEAKING ? 1f : 0f) - speakMix) * Math.min(1f, dt * 3f);
        listenMix += ((s == LISTENING ? 1f : 0f) - listenMix) * Math.min(1f, dt * 3f);
        spin += dt * (0.25f + 1.6f * think + 0.6f * energy);
        for (int k = 0; k < 3; k++) lerpRgb(col[k], PALETTE[s][k], Math.min(1f, dt * 3.5f));
        float pulseAge = (now - pulseAt) / 1e9f;
        float pulse = pulseAge < 1.4f ? 1f - pulseAge / 1.4f : 0f;

        // ---- geometry -------------------------------------------------------------------------------
        int w = getWidth(), h = getHeight();
        float cx = w / 2f, cy = h / 2f;
        float R = Math.min(w, h) * 0.30f * (1f + 0.06f * level + 0.05f * pulse * pulse);

        // Ambient halo
        float haloR = R * (2.0f + 0.5f * energy);
        glow.setShader(new RadialGradient(cx, cy, haloR,
                new int[]{argb(0.34f + 0.3f * energy, col[1]), argb(0.12f + 0.1f * energy, col[0]), Color.TRANSPARENT},
                new float[]{0f, 0.45f, 1f}, Shader.TileMode.CLAMP));
        c.drawCircle(cx, cy, haloR, glow);

        // Expanding event ring
        if (pulse > 0f) {
            float pr = R * (1.05f + (1f - pulse) * 0.95f);
            stroke.setShader(null); stroke.setStrokeWidth(density * (1f + 3f * pulse));
            stroke.setColor(argb(0.55f * pulse, col[2])); c.drawCircle(cx, cy, pr, stroke);
            stroke.setColor(argb(0.25f * pulse, col[0])); c.drawCircle(cx, cy, pr * 0.92f, stroke);
        }

        // 3D particle sphere
        float tilt = 0.42f + 0.12f * (float) Math.sin(t * 0.35);
        float cY = (float) Math.cos(spin), sY = (float) Math.sin(spin), cX = (float) Math.cos(tilt), sX = (float) Math.sin(tilt);
        float amp = 0.035f + 0.26f * energy;
        float focal = 3.2f;
        for (int i = 0; i < ux.length; i++) {
            float la = lat01[i], lo = lon01[i];
            float n = (float) (Math.sin(lo * 18.85 + t * 2.1 + la * 6.0) * Math.cos(la * 12.6 - t * 1.4)) * 0.55f
                    + (float) Math.sin(la * 25.1 + lo * 12.57 - t * 3.3) * (0.25f + 0.55f * level)
                    + (float) Math.sin(lo * 37.7 - t * 5.0 + la * 3.0) * 0.35f * think;
            float d = 1f + amp * n * poleW[i];
            float x = ux[i] * d, y = uy[i] * d, z = uz[i] * d;
            float x1 = x * cY + z * sY, z1 = -x * sY + z * cY;           // spin around Y
            float y2 = y * cX - z1 * sX, z2 = y * sX + z1 * cX;          // tilt around X
            float k = focal / (focal - z2);
            float depth = (z2 + 1.25f) / 2.5f;                           // 0 = back, 1 = front
            if (depth < 0f) depth = 0f; else if (depth > 1f) depth = 1f;
            float mix = (lo + t * 0.04f + la * 0.3f) % 1f;
            int rgb = tri(mix, depth);
            float alpha = 0.10f + 0.85f * depth * depth;
            dot.setColor(argb(alpha * (0.75f + 0.25f * energy), rgb));
            c.drawCircle(cx + x1 * R * k, cy + y2 * R * k, density * (0.7f + 1.7f * depth) * k, dot);
        }

        // Inner core
        float coreR = R * (0.62f + 0.18f * level);
        fill.setShader(new RadialGradient(cx, cy, coreR,
                new int[]{argb(0.55f + 0.35f * level, mixWhite(col[2], 0.55f)), argb(0.30f, col[0]), Color.TRANSPARENT},
                new float[]{0f, 0.35f, 1f}, Shader.TileMode.CLAMP));
        c.drawCircle(cx, cy, coreR, fill);
        fill.setShader(null);

        // Siri-style ribbons through the equator
        float span = R * 1.55f;
        float ribbonAmp = R * (0.03f + 0.62f * level * (0.45f + 0.55f * Math.max(listenMix, speakMix)) + 0.10f * think);
        for (int r = 0; r < 3; r++) {
            float freq = 1.6f + r * 0.55f, speed = 2.4f + r * 1.3f, ph = r * 2.1f;
            float a = ribbonAmp * (1f - r * 0.22f);
            path.reset();
            int steps = 72;
            for (int j = 0; j <= steps; j++) {
                float u = -1f + 2f * j / steps;
                float env = (float) Math.pow(4f / (4f + Math.pow(u * 2.2f, 4)), 4);
                float yv = (float) Math.sin(u * Math.PI * freq + t * speed + ph) * a * env;
                float px = cx + u * span;
                if (j == 0) path.moveTo(px, cy + yv); else path.lineTo(px, cy + yv);
            }
            for (int j = steps; j >= 0; j--) {
                float u = -1f + 2f * j / steps;
                float env = (float) Math.pow(4f / (4f + Math.pow(u * 2.2f, 4)), 4);
                float yv = (float) Math.sin(u * Math.PI * freq + t * speed + ph + 0.9f) * a * env * 0.35f;
                path.lineTo(cx + u * span, cy - yv);
            }
            path.close();
            fill.setShader(fade(cx, span, argb(0.22f + 0.25f * level, col[r])));
            c.drawPath(path, fill);
            stroke.setShader(fade(cx, span, argb(0.45f + 0.4f * level, mixWhite(col[r], 0.25f)))); stroke.setStrokeWidth(density * 1.4f);
            c.drawPath(path, stroke);
            fill.setShader(null); stroke.setShader(null);
        }

        // Thinking: orbiting arcs
        if (think > 0.02f) {
            float ar = R * 1.22f;
            arc.set(cx - ar, cy - ar, cx + ar, cy + ar);
            stroke.setStrokeWidth(density * 2.2f);
            stroke.setColor(argb(0.75f * think, col[2]));
            c.drawArc(arc, (t * 220f) % 360f, 70f, false, stroke);
            stroke.setColor(argb(0.55f * think, col[0]));
            c.drawArc(arc, (t * 220f + 180f) % 360f, 40f, false, stroke);
            ar = R * 1.32f; arc.set(cx - ar, cy - ar, cx + ar, cy + ar);
            stroke.setStrokeWidth(density * 1.2f);
            stroke.setColor(argb(0.4f * think, col[1]));
            c.drawArc(arc, 360f - (t * 140f) % 360f, 110f, false, stroke);
        }

        if (isAttachedToWindow() && getVisibility() == VISIBLE) postInvalidateOnAnimation();
    }

    /** Horizontal fade so ribbons melt into the halo instead of ending in a hard line. */
    private static Shader fade(float cx, float span, int color) {
        int clear = color & 0x00FFFFFF;
        return new LinearGradient(cx - span, 0, cx + span, 0, new int[]{clear, color, color, clear}, new float[]{0f, 0.3f, 0.7f, 1f}, Shader.TileMode.CLAMP);
    }

    // ---- colour helpers ---------------------------------------------------------------------------
    private int tri(float m, float depth) {
        float[] a, bb; float f;
        if (m < 0.5f) { a = col[0]; bb = col[1]; f = m * 2f; } else { a = col[1]; bb = col[2]; f = (m - 0.5f) * 2f; }
        f = f * f * (3 - 2 * f);
        float lift = 0.25f * depth * depth;                      // front particles catch the light
        return Color.rgb(clamp((a[0] + (bb[0] - a[0]) * f) * (1 - lift) + 255 * lift),
                clamp((a[1] + (bb[1] - a[1]) * f) * (1 - lift) + 255 * lift),
                clamp((a[2] + (bb[2] - a[2]) * f) * (1 - lift) + 255 * lift));
    }
    private static int mixWhite(float[] c, float f) { return Color.rgb(clamp(c[0] + (255 - c[0]) * f), clamp(c[1] + (255 - c[1]) * f), clamp(c[2] + (255 - c[2]) * f)); }
    private static int argb(float a, float[] c) { return Color.argb(clamp(a * 255), clamp(c[0]), clamp(c[1]), clamp(c[2])); }
    private static int argb(float a, int rgb) { return (clamp(a * 255) << 24) | (rgb & 0xFFFFFF); }
    private static int clamp(float v) { return v < 0 ? 0 : v > 255 ? 255 : Math.round(v); }
    private static void setRgb(float[] o, int c) { o[0] = Color.red(c); o[1] = Color.green(c); o[2] = Color.blue(c); }
    private static void lerpRgb(float[] o, int c, float f) { o[0] += (Color.red(c) - o[0]) * f; o[1] += (Color.green(c) - o[1]) * f; o[2] += (Color.blue(c) - o[2]) * f; }
}
