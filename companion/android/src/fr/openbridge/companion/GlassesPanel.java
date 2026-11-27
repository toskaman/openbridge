package fr.openbridge.companion;

import java.io.ByteArrayOutputStream;
import java.text.Normalizer;

/** Draws glasses screens on the phone, for standalone mode. Same rules as the PC's display engine
 *  (src/glasses/panel.py), measured on a real ENGO 3 on 26 Nov 2026: logical (x, y) is sent as (303 - x, 255 - y),
 *  upright text is rotation 4 anchored at its logical top-left, fonts 0-5 are 24/24/38/64/75/82 px tall with letters
 *  about half as wide, ASCII only, and the visible window is x 12-284, y 4-234. */
final class GlassesPanel {
    static final int W = 304, H = 256, X0 = 12, X1 = 284, Y0 = 4, Y1 = 234, CX = (X0 + X1) / 2;
    static final int[] FONT_H = {24, 24, 38, 64, 75, 82};
    /** Tones as red-green palette values (colour glasses) and grey levels (ENGO 1 / 2). */
    static final int PRIMARY = 0xff, SECONDARY = 0xbf, MUTED = 0x7b, ACCENT = 0x87, OK = 0xc3, WARN = 0x3e, ALERT = 0x3c;
    private static final int[][] GREY = {{0xff, 15}, {0xbf, 12}, {0x7b, 8}, {0x87, 13}, {0xc3, 13}, {0x3e, 11}, {0x3c, 10}};

    private final ByteArrayOutputStream out = new ByteArrayOutputStream();
    private final boolean colour;
    private int ink = -1;

    GlassesPanel(boolean colour) { this.colour = colour; }

    GlassesPanel begin() { put(AL.hold(false)); put(AL.clear()); ink = -1; return this; }
    byte[] end() { put(AL.hold(true)); return out.toByteArray(); }

    private void put(byte[] b) { out.write(b, 0, b.length); }
    private static int fx(int x) { return W - 1 - x; }
    private static int fy(int y) { return H - 1 - y; }
    private static int grey(int tone) { for (int[] g : GREY) if (g[0] == tone) return g[1]; return 15; }

    private void ink(int tone) {
        if (tone == ink) return;
        put(colour ? AL.colour(tone) : AL.grey(grey(tone)));
        ink = tone;
    }

    static String ascii(String s) {
        if (s == null) return "";
        String n = Normalizer.normalize(s.replace('’', '\'').replace('«', '"').replace('»', '"').replace('œ', 'o').replace('€', 'E'), Normalizer.Form.NFKD);
        StringBuilder b = new StringBuilder();
        for (char c : n.toCharArray()) if (c >= 32 && c < 127) b.append(c);
        return b.toString().replaceAll("\\s+", " ").trim();
    }

    static int width(String s, int font) { return ascii(s).length() * FONT_H[font] / 2; }

    static String fit(String s, int font, int w) {
        String t = ascii(s);
        if (width(t, font) <= w) return t;
        while (t.length() > 0 && width(t + "...", font) > w) t = t.substring(0, t.length() - 1);
        return t.trim() + "...";
    }

    /** Words wrapped to `w`, at most `max` lines (the last one cut with "..."). */
    static java.util.List<String> wrap(String s, int font, int w, int max) {
        java.util.List<String> lines = new java.util.ArrayList<>();
        String cur = "";
        for (String word : ascii(s).split(" ")) {
            String next = cur.isEmpty() ? word : cur + " " + word;
            if (width(next, font) <= w) { cur = next; continue; }
            if (!cur.isEmpty()) lines.add(cur);
            cur = word;
            if (lines.size() == max) break;
        }
        if (lines.size() < max && !cur.isEmpty()) lines.add(cur);
        if (lines.size() == max && !String.join(" ", lines).equals(ascii(s))) lines.set(max - 1, fit(lines.get(max - 1) + " ...", font, w));
        return lines;
    }

    int text(int x, int y, String s, int font, int tone) {
        String t = ascii(s);
        if (t.isEmpty()) return 0;
        if (colour) put(AL.text(fx(x), fy(y), 4, font, tone, true, t));
        else { put(AL.text(fx(x), fy(y), 4, font, grey(tone), false, t)); }
        ink = -1;                                   // text carries its own colour
        return width(t, font);
    }
    /** Centred, and cut to the visible width so it never runs past the edges. */
    int center(int cx, int y, String s, int font, int tone) {
        String t = fit(s, font, X1 - X0);
        return text(cx - width(t, font) / 2, y, t, font, tone);
    }
    int right(int xr, int y, String s, int font, int tone) { return text(xr - width(s, font), y, s, font, tone); }

    void line(int x0, int y0, int x1, int y1, int tone) { ink(tone); put(AL.line(fx(x0), fy(y0), fx(x1), fy(y1))); }
    void rect(int x0, int y0, int x1, int y1, int tone, boolean fill) {
        ink(tone);
        put(AL.rect(Math.min(fx(x0), fx(x1)), Math.min(fy(y0), fy(y1)), Math.max(fx(x0), fx(x1)), Math.max(fy(y0), fy(y1)), fill));
    }
    void circle(int cx, int cy, int r, int tone, boolean fill) { ink(tone); put(AL.circle(fx(cx), fy(cy), r, fill)); }
    /** Degrees, 0 at 3 o'clock, clockwise; device angle = logical angle, start in 0-359. */
    void arc(int cx, int cy, int r, int start, int end, int tone) {
        ink(tone);
        int sweep = end - start, st = ((start % 360) + 360) % 360;
        put(AL.arc(fx(cx), fy(cy), r, st, st + sweep));
    }
    void roundRect(int x0, int y0, int x1, int y1, int r, int tone) {
        line(x0 + r, y0, x1 - r, y0, tone); line(x0 + r, y1, x1 - r, y1, tone);
        line(x0, y0 + r, x0, y1 - r, tone); line(x1, y0 + r, x1, y1 - r, tone);
        arc(x0 + r, y0 + r, r, 180, 270, tone); arc(x1 - r, y0 + r, r, 270, 360, tone);
        arc(x1 - r, y1 - r, r, 0, 90, tone); arc(x0 + r, y1 - r, r, 90, 180, tone);
    }
}
