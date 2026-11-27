package fr.openbridge.companion;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

/** What the glasses show, drawn on the phone: every ActiveLook frame written to the glasses is also parsed here and
 *  drawn on a 304 x 256 picture, the right way up, as the wearer sees it (the same rules as HUD Studio and the
 *  emulator, measured on a real ENGO 3 on 26 Nov 2026: both axes mirrored, upright text = rotation 4 anchored at its
 *  top-left, grey levels look yellow, colours from the 81-value red-green palette).
 *
 *  It only reads bytes that were already going to the glasses; it never writes anything. */
final class FrameMirror {
    static final int W = 304, H = 256;
    interface Listener { void frame(Bitmap b); }

    private static final int[][] RG = {
            {0x00, 0x01, 0x02, 0x41, 0x81, 0x82, 0x43, 0x83, 0xc3},
            {0x04, 0x05, 0x06, 0x45, 0x85, 0x86, 0x47, 0x87, 0xc7},
            {0x20, 0x21, 0x22, 0x61, 0xa1, 0xa2, 0x63, 0xa3, 0xe3},
            {0x14, 0x15, 0x16, 0x55, 0x95, 0x96, 0x57, 0x97, 0xd7},
            {0x18, 0x19, 0x1a, 0x59, 0x99, 0x9a, 0x5b, 0x9b, 0xdb},
            {0x28, 0x29, 0x2a, 0x69, 0xa9, 0xaa, 0x6b, 0xab, 0xeb},
            {0x1c, 0x1d, 0x1e, 0x5d, 0x9d, 0x9e, 0x5f, 0x9f, 0xdf},
            {0x38, 0x39, 0x3a, 0x79, 0xb9, 0xba, 0x7b, 0xbb, 0xfb},
            {0x3c, 0x3d, 0x3e, 0x7d, 0xbd, 0xbe, 0x7f, 0xbf, 0xff}};
    private static final int[] FONT_PX = {19, 19, 30, 51, 60, 66};

    private final Bitmap back = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888);
    private final Canvas canvas = new Canvas(back);
    private final Paint shape = new Paint(Paint.ANTI_ALIAS_FLAG), text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ByteArrayOutputStream buf = new ByteArrayOutputStream();
    private int ink = grey(15);
    private boolean hold, dirty;
    private volatile Listener listener;
    private volatile Bitmap front;
    long frames;

    FrameMirror() {
        canvas.drawColor(Color.BLACK);
        text.setTypeface(Typeface.create("sans-serif-condensed", Typeface.NORMAL));
        shape.setStrokeWidth(1f);
    }

    void setListener(Listener l) { listener = l; if (l != null && front != null) l.frame(front); }
    Bitmap last() { return front; }

    static int grey(int level) {
        int lv = Math.max(0, Math.min(15, level)) * 255 / 15;
        return Color.rgb(255 * lv / 255, 214 * lv / 255, 10 * lv / 255);
    }

    static int rg(int v) {
        for (int r = 0; r < 9; r++) for (int g = 0; g < 9; g++) if (RG[r][g] == (v & 0xff)) return Color.rgb(r * 255 / 8, g * 255 / 8, 0);
        return Color.BLACK;
    }

    /** Bytes as they went to the glasses (any chunking). */
    synchronized void feed(byte[] chunk) {
        buf.write(chunk, 0, chunk.length);
        byte[] b = buf.toByteArray();
        int i = 0;
        while (i < b.length) {
            if ((b[i] & 0xff) != 0xFF) { i++; continue; }
            if (i + 4 > b.length) break;
            int fmt = b[i + 2] & 0xff;
            boolean wide = (fmt & 0x20) != 0;
            int head = wide ? 5 : 4;
            if (i + head > b.length) break;
            int len = wide ? ((b[i + 3] & 0xff) << 8) | (b[i + 4] & 0xff) : (b[i + 3] & 0xff);
            int q = (fmt >> 1) & 0x0F;
            if (len < head + q + 1) { i++; continue; }
            if (i + len > b.length) break;
            if ((b[i + len - 1] & 0xff) != 0xAA) { i++; continue; }
            int start = i + head + q, n = len - head - q - 1;
            try { draw(b[i + 1] & 0xff, b, start, n); } catch (Exception ignored) { }
            i += len;
        }
        buf.reset();
        if (i < b.length && b.length - i < 4096) buf.write(b, i, b.length - i);
        if (dirty && !hold) publish();
    }

    private void publish() {
        dirty = false;
        frames++;
        Bitmap copy = back.copy(Bitmap.Config.ARGB_8888, false);
        front = copy;
        Listener l = listener;
        if (l != null) try { l.frame(copy); } catch (Exception ignored) { }
    }

    private static int s16(byte[] b, int o) { return (short) (((b[o] & 0xff) << 8) | (b[o + 1] & 0xff)); }
    private static float vx(int x) { return W - 1 - x; }
    private static float vy(int y) { return H - 1 - y; }

    private void draw(int cmd, byte[] b, int o, int n) {
        if (cmd != 0x39 && cmd != 0x30 && cmd != 0x3D) dirty = true;
        switch (cmd) {
            case 0x01: canvas.drawColor(Color.BLACK); break;
            case 0x30: if (n >= 1) ink = grey(b[o]); break;
            case 0x3D: if (n >= 1) ink = rg(b[o]); break;
            case 0x39: if (n >= 1) { hold = b[o] == 0; if (!hold) publish(); } break;
            case 0x31: if (n >= 4) { shape.setColor(ink); canvas.drawPoint(vx(s16(b, o)), vy(s16(b, o + 2)), shape); } break;
            case 0x32: if (n >= 8) { shape.setColor(ink); shape.setStyle(Paint.Style.STROKE);
                canvas.drawLine(vx(s16(b, o)), vy(s16(b, o + 2)), vx(s16(b, o + 4)), vy(s16(b, o + 6)), shape); } break;
            case 0x33: case 0x34: if (n >= 8) {
                float x0 = vx(s16(b, o)), y0 = vy(s16(b, o + 2)), x1 = vx(s16(b, o + 4)), y1 = vy(s16(b, o + 6));
                shape.setColor(ink); shape.setStyle(cmd == 0x34 ? Paint.Style.FILL : Paint.Style.STROKE);
                canvas.drawRect(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1) + (cmd == 0x34 ? 1 : 0), Math.max(y0, y1) + (cmd == 0x34 ? 1 : 0), shape);
            } break;
            case 0x35: case 0x36: if (n >= 5) {
                shape.setColor(ink); shape.setStyle(cmd == 0x36 ? Paint.Style.FILL : Paint.Style.STROKE);
                canvas.drawCircle(vx(s16(b, o)), vy(s16(b, o + 2)), b[o + 4] & 0xff, shape);
            } break;
            case 0x3C: if (n >= 9) {
                float x = vx(s16(b, o)), y = vy(s16(b, o + 2)); int r = b[o + 4] & 0xff;
                int st = s16(b, o + 5), en = s16(b, o + 7);
                shape.setColor(ink); shape.setStyle(Paint.Style.STROKE);
                canvas.drawArc(new RectF(x - r, y - r, x + r, y + r), st, en - st, false, shape);
            } break;
            case 0x37: case 0x3E: if (n >= 7) {
                int x = s16(b, o), y = s16(b, o + 2), rot = b[o + 4] & 0xff, font = b[o + 5] & 0xff, col = b[o + 6] & 0xff;
                int end = o + 7; while (end < o + n && b[end] != 0) end++;
                String s = new String(b, o + 7, end - (o + 7), StandardCharsets.UTF_8);
                text.setColor(cmd == 0x3E ? rg(col) : grey(col));
                text.setTextSize(FONT_PX[Math.min(font, FONT_PX.length - 1)]);
                float top = -text.getFontMetrics().top * 0.92f;
                float ax = vx(x), ay = vy(y);
                if (rot == 4) canvas.drawText(s, ax, ay + top, text);
                else { canvas.save(); canvas.rotate(180, ax, ay); canvas.drawText(s, ax, ay + top, text); canvas.restore(); }
            } break;
            default: break;
        }
    }
}
