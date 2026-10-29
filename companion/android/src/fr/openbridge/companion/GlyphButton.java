package fr.openbridge.companion;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.util.TypedValue;
import android.view.View;

/** Round, focusable icon button drawn on Canvas (mic, stop, send): no bitmaps, crisp at any size, D-pad friendly. */
public class GlyphButton extends View {
    public static final int MIC = 0, STOP = 1, SEND = 2;
    private int glyph;
    private int accent;
    private boolean active;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final RectF r = new RectF();
    private final float dp;

    public GlyphButton(Context c, int glyph, int accent) {
        super(c);
        this.glyph = glyph; this.accent = accent;
        dp = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, 1, c.getResources().getDisplayMetrics());
        setFocusable(true); setClickable(true);
        setContentDescription(glyph == SEND ? "Send" : glyph == STOP ? "Stop recording" : "Speak");
    }

    public void setGlyph(int g) { glyph = g; setContentDescription(g == SEND ? "Send" : g == STOP ? "Stop recording" : "Speak"); invalidate(); }
    /** Active = filled with the accent colour (recording, or text ready to send). */
    public void setActive(boolean a) { if (a != active) { active = a; invalidate(); } }
    public void setAccent(int a) { accent = a; invalidate(); }
    @Override protected void drawableStateChanged() { super.drawableStateChanged(); invalidate(); }

    @Override protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight(), cx = w / 2f, cy = h / 2f, rad = Math.min(w, h) / 2f - dp * 2;
        boolean focus = isFocused(), pressed = isPressed();
        p.setStyle(Paint.Style.FILL); p.setShader(null);
        if (active || pressed) {
            p.setShader(new RadialGradient(cx, cy - rad * 0.4f, rad * 1.5f, lighten(accent, 0.35f), accent, Shader.TileMode.CLAMP));
            c.drawCircle(cx, cy, rad, p); p.setShader(null);
        } else {
            p.setColor(Color.argb(28, 255, 255, 255)); c.drawCircle(cx, cy, rad, p);
        }
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(focus ? dp * 3 : dp);
        p.setColor(focus ? Color.WHITE : active ? lighten(accent, 0.4f) : Color.argb(60, 255, 255, 255));
        c.drawCircle(cx, cy, rad, p);

        int ink = active || pressed ? Color.rgb(8, 10, 20) : Color.rgb(232, 236, 255);
        p.setColor(ink);
        float u = rad * 0.5f;
        if (glyph == MIC) {
            p.setStyle(Paint.Style.FILL);
            r.set(cx - u * 0.36f, cy - u * 0.95f, cx + u * 0.36f, cy + u * 0.25f);
            c.drawRoundRect(r, u * 0.36f, u * 0.36f, p);
            p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(dp * 2f); p.setStrokeCap(Paint.Cap.ROUND);
            r.set(cx - u * 0.68f, cy - u * 0.55f, cx + u * 0.68f, cy + u * 0.62f);
            c.drawArc(r, 0, 180, false, p);
            c.drawLine(cx, cy + u * 0.62f, cx, cy + u * 0.92f, p);
            c.drawLine(cx - u * 0.36f, cy + u * 0.92f, cx + u * 0.36f, cy + u * 0.92f, p);
        } else if (glyph == STOP) {
            p.setStyle(Paint.Style.FILL);
            r.set(cx - u * 0.48f, cy - u * 0.48f, cx + u * 0.48f, cy + u * 0.48f);
            c.drawRoundRect(r, u * 0.14f, u * 0.14f, p);
        } else {
            p.setStyle(Paint.Style.FILL);
            path.reset();
            path.moveTo(cx - u * 0.70f, cy - u * 0.78f);
            path.lineTo(cx + u * 0.85f, cy);
            path.lineTo(cx - u * 0.70f, cy + u * 0.78f);
            path.lineTo(cx - u * 0.42f, cy);
            path.close();
            c.drawPath(path, p);
        }
    }

    static int lighten(int c, float f) {
        return Color.rgb(Math.round(Color.red(c) + (255 - Color.red(c)) * f), Math.round(Color.green(c) + (255 - Color.green(c)) * f),
                Math.round(Color.blue(c) + (255 - Color.blue(c)) * f));
    }
}
