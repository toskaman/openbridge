package fr.openbridge.companion;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;

/**
 * Small vector icons for the companion's buttons (no bitmaps, crisp at any density), plus the
 * on/off switch shown at the end of toggle buttons. Drawn with anti-aliased strokes in one colour.
 */
public class PillIcon extends Drawable {
    public static final int SPARK = 0, BLUETOOTH = 1, PIN = 2, SHIELD = 3, PAUSE = 4, PLAY = 5, BOLT = 6, UNLINK = 7,
            FLOWS = 8, HOLD = 9, SWITCH = 10;

    private final int kind, sizePx, wPx;
    private final float dp;
    private int color;
    private boolean on;                 // SWITCH only
    private int accent;                 // SWITCH only
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF r = new RectF();

    public PillIcon(int kind, int color, float dp) {
        this.kind = kind; this.color = color; this.dp = dp;
        sizePx = Math.round((kind == SWITCH ? 18 : 20) * dp);
        wPx = kind == SWITCH ? Math.round(32 * dp) : sizePx;
        p.setStrokeCap(Paint.Cap.ROUND); p.setStrokeJoin(Paint.Join.ROUND);
    }
    public static PillIcon toggle(boolean on, int accent, float dp) { PillIcon s = new PillIcon(SWITCH, 0, dp); s.on = on; s.accent = accent; return s; }

    @Override public int getIntrinsicWidth() { return wPx; }
    @Override public int getIntrinsicHeight() { return sizePx; }
    @Override public void setAlpha(int a) { }
    @Override public void setColorFilter(ColorFilter cf) { }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }

    @Override public void draw(Canvas c) {
        float w = getBounds().width(), h = getBounds().height();
        if (w <= 0 || h <= 0) return;
        c.save(); c.translate(getBounds().left, getBounds().top);
        if (kind == SWITCH) { drawSwitch(c, w, h); c.restore(); return; }
        float s = Math.min(w, h) / 20f, cx = w / 2f, cy = h / 2f;     // 20-unit design grid
        p.setColor(color); p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1.8f * s);
        path.reset();
        switch (kind) {
            case SPARK:
                path.moveTo(cx, cy - 8 * s); path.quadTo(cx + 1 * s, cy - 1 * s, cx + 8 * s, cy);
                path.quadTo(cx + 1 * s, cy + 1 * s, cx, cy + 8 * s); path.quadTo(cx - 1 * s, cy + 1 * s, cx - 8 * s, cy);
                path.quadTo(cx - 1 * s, cy - 1 * s, cx, cy - 8 * s); c.drawPath(path, p);
                break;
            case BLUETOOTH:
                path.moveTo(cx - 5 * s, cy - 4.5f * s); path.lineTo(cx + 4.5f * s, cy + 4.5f * s); path.lineTo(cx, cy + 9 * s);
                path.lineTo(cx, cy - 9 * s); path.lineTo(cx + 4.5f * s, cy - 4.5f * s); path.lineTo(cx - 5 * s, cy + 4.5f * s);
                c.drawPath(path, p);
                break;
            case PIN:
                r.set(cx - 6 * s, cy - 8.5f * s, cx + 6 * s, cy + 3.5f * s);
                path.addArc(r, 140, 260); path.lineTo(cx, cy + 9 * s); path.close(); c.drawPath(path, p);
                c.drawCircle(cx, cy - 2.5f * s, 2.2f * s, p);
                break;
            case SHIELD:
                path.moveTo(cx, cy - 8.5f * s); path.lineTo(cx + 7 * s, cy - 5.5f * s); path.quadTo(cx + 7 * s, cy + 5 * s, cx, cy + 9 * s);
                path.quadTo(cx - 7 * s, cy + 5 * s, cx - 7 * s, cy - 5.5f * s); path.close(); c.drawPath(path, p);
                path.reset(); path.moveTo(cx - 3 * s, cy); path.lineTo(cx - 0.5f * s, cy + 2.5f * s); path.lineTo(cx + 3.5f * s, cy - 2.5f * s);
                c.drawPath(path, p);
                break;
            case PAUSE:
                c.drawLine(cx - 3 * s, cy - 6 * s, cx - 3 * s, cy + 6 * s, p); c.drawLine(cx + 3 * s, cy - 6 * s, cx + 3 * s, cy + 6 * s, p);
                break;
            case PLAY:
                path.moveTo(cx - 4 * s, cy - 6.5f * s); path.lineTo(cx + 6 * s, cy); path.lineTo(cx - 4 * s, cy + 6.5f * s); path.close();
                c.drawPath(path, p);
                break;
            case BOLT:
                path.moveTo(cx + 2 * s, cy - 9 * s); path.lineTo(cx - 5 * s, cy + 1.5f * s); path.lineTo(cx, cy + 1.5f * s);
                path.lineTo(cx - 2 * s, cy + 9 * s); path.lineTo(cx + 5 * s, cy - 1.5f * s); path.lineTo(cx, cy - 1.5f * s); path.close();
                c.drawPath(path, p);
                break;
            case UNLINK:                                          /* two chain halves pulled apart + spark ticks */
                path.moveTo(cx - 2.5f * s, cy - 4.5f * s); path.lineTo(cx - 6 * s, cy - 4.5f * s);
                path.quadTo(cx - 10.5f * s, cy - 4.5f * s, cx - 10.5f * s, cy); path.quadTo(cx - 10.5f * s, cy + 4.5f * s, cx - 6 * s, cy + 4.5f * s);
                path.lineTo(cx - 2.5f * s, cy + 4.5f * s);
                path.moveTo(cx + 2.5f * s, cy - 4.5f * s); path.lineTo(cx + 6 * s, cy - 4.5f * s);
                path.quadTo(cx + 10.5f * s, cy - 4.5f * s, cx + 10.5f * s, cy); path.quadTo(cx + 10.5f * s, cy + 4.5f * s, cx + 6 * s, cy + 4.5f * s);
                path.lineTo(cx + 2.5f * s, cy + 4.5f * s);
                c.drawPath(path, p);
                c.drawLine(cx, cy - 9 * s, cx, cy - 7 * s, p); c.drawLine(cx, cy + 7 * s, cx, cy + 9 * s, p);
                c.drawLine(cx - 4 * s, cy - 8.5f * s, cx - 3 * s, cy - 7 * s, p); c.drawLine(cx + 4 * s, cy + 8.5f * s, cx + 3 * s, cy + 7 * s, p);
                break;
            case FLOWS: {
                p.setStyle(Paint.Style.FILL); c.drawCircle(cx, cy, 2.6f * s, p);
                double[] an = {-0.5, 1.6, 3.6};
                for (double a : an) {
                    float ux = (float) Math.cos(a), uy = (float) Math.sin(a);
                    p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1.3f * s); p.setAlpha(150);
                    c.drawLine(cx + ux * 4.2f * s, cy + uy * 4.2f * s, cx + ux * 7f * s, cy + uy * 7f * s, p);
                    p.setAlpha(255); p.setStyle(Paint.Style.FILL);
                    c.drawCircle(cx + ux * 8.4f * s, cy + uy * 8.4f * s, 1.8f * s, p);
                }
                break;
            }
            case HOLD:
                c.drawCircle(cx, cy, 3 * s, p);
                p.setAlpha(140); c.drawCircle(cx, cy, 6.5f * s, p);
                p.setAlpha(70); c.drawCircle(cx, cy, 9.2f * s, p); p.setAlpha(255);
                break;
            default: break;
        }
        c.restore();
    }

    private void drawSwitch(Canvas c, float w, float h) {
        float th = h * 0.78f, ty = (h - th) / 2f;
        r.set(1, ty, w - 1, ty + th);
        p.setStyle(Paint.Style.FILL);
        p.setColor(on ? (accent & 0x00FFFFFF) | 0x8C000000 : 0xFF2A3150);
        c.drawRoundRect(r, th / 2, th / 2, p);
        p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(dp);
        p.setColor(on ? accent : 0xFF5C6484);
        c.drawRoundRect(r, th / 2, th / 2, p);
        p.setStyle(Paint.Style.FILL);
        p.setColor(on ? 0xFFFFFFFF : 0xFF9AA3C7);
        float kr = th / 2f - 2.5f * dp;
        c.drawCircle(on ? w - 1 - th / 2 : 1 + th / 2, ty + th / 2, kr, p);
    }
}
