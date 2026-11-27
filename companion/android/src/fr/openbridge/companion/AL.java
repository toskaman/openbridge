package fr.openbridge.companion;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

/** ActiveLook frames built on the phone: 0xFF cmd fmt len [data] 0xAA (len counts the whole frame; fmt bit 5 = two-byte
 *  length). Same encoding as src/adapters/activelook.py on the PC. */
final class AL {
    private AL() { }

    static byte[] frame(int cmd, byte[] data) {
        int len = 5 + data.length;
        boolean wide = len > 255;
        if (wide) len++;
        ByteArrayOutputStream o = new ByteArrayOutputStream(len);
        o.write(0xFF); o.write(cmd); o.write(wide ? 0x20 : 0x00);
        if (wide) { o.write(len >> 8); o.write(len & 0xff); } else o.write(len);
        o.write(data, 0, data.length);
        o.write(0xAA);
        return o.toByteArray();
    }

    static byte[] luma(int level) { return frame(0x10, new byte[]{(byte) Math.max(0, Math.min(15, level))}); }
    static byte[] clear() { return frame(0x01, new byte[0]); }
    static byte[] hold(boolean flush) { return frame(0x39, new byte[]{(byte) (flush ? 1 : 0)}); }
    static byte[] grey(int level) { return frame(0x30, new byte[]{(byte) Math.max(0, Math.min(15, level))}); }
    static byte[] colour(int rg) { return frame(0x3D, new byte[]{(byte) rg}); }
    static byte[] gestureOn() { return cat(frame(0x20, new byte[]{1}), frame(0x21, new byte[]{1})); }

    private static byte[] s16(int... v) {
        byte[] b = new byte[v.length * 2];
        for (int i = 0; i < v.length; i++) { b[2 * i] = (byte) (v[i] >> 8); b[2 * i + 1] = (byte) v[i]; }
        return b;
    }

    static byte[] line(int x0, int y0, int x1, int y1) { return frame(0x32, s16(x0, y0, x1, y1)); }
    static byte[] rect(int x0, int y0, int x1, int y1, boolean fill) { return frame(fill ? 0x34 : 0x33, s16(x0, y0, x1, y1)); }
    static byte[] circle(int x, int y, int r, boolean fill) { return frame(fill ? 0x36 : 0x35, cat(s16(x, y), new byte[]{(byte) r})); }
    static byte[] arc(int x, int y, int r, int start, int end) { return frame(0x3C, cat(s16(x, y), new byte[]{(byte) r}, s16(start, end), new byte[]{1})); }

    /** Text: rg >= 0 uses the colour command (ENGO 3), otherwise a grey level. */
    static byte[] text(int x, int y, int rot, int font, int rgOrGrey, boolean colour, String s) {
        byte[] t = s.getBytes(StandardCharsets.US_ASCII);
        if (t.length > 250) t = java.util.Arrays.copyOf(t, 250);
        return frame(colour ? 0x3E : 0x37, cat(s16(x, y), new byte[]{(byte) rot, (byte) font, (byte) rgOrGrey}, t, new byte[]{0}));
    }

    static byte[] cat(byte[]... parts) {
        ByteArrayOutputStream o = new ByteArrayOutputStream();
        for (byte[] p : parts) o.write(p, 0, p.length);
        return o.toByteArray();
    }
}
