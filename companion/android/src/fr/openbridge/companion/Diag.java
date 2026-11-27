package fr.openbridge.companion;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Diagnostics kept in memory only (never on disk, never sent unless the owner exports them): the last events of the
 *  Companion, and how long each relay operation took to answer. */
final class Diag {
    private static final int MAX = 300;
    private static final ArrayDeque<String> lines = new ArrayDeque<>();
    private static final Map<String, long[]> ops = new LinkedHashMap<>();   // op -> {count, last ms, total ms, max ms}
    private static final SimpleDateFormat TIME = new SimpleDateFormat("HH:mm:ss", Locale.ROOT);

    private Diag() { }

    static synchronized void log(String s) {
        if (s == null) return;
        lines.add(TIME.format(new Date()) + "  " + (s.length() > 200 ? s.substring(0, 200) : s));
        while (lines.size() > MAX) lines.poll();
    }

    static synchronized void op(String op, long ms) {
        if (op == null) return;
        long[] v = ops.get(op);
        if (v == null) { v = new long[4]; ops.put(op, v); }
        v[0]++; v[1] = ms; v[2] += ms; v[3] = Math.max(v[3], ms);
        if (!op.startsWith("glasses_") && !"get_requests".equals(op) && !"get_commands".equals(op)) log("PC: " + op + " (" + ms + " ms)");
    }

    static synchronized String opsText() {
        StringBuilder b = new StringBuilder();
        for (Map.Entry<String, long[]> e : ops.entrySet()) {
            long[] v = e.getValue();
            b.append(String.format(Locale.ROOT, "%-20s ×%-5d last %4d ms  avg %4d ms  max %4d ms%n", e.getKey(), v[0], v[1], v[0] == 0 ? 0 : v[2] / v[0], v[3]));
        }
        return b.length() == 0 ? "—" : b.toString();
    }

    static synchronized String logText() {
        StringBuilder b = new StringBuilder();
        for (String l : lines) b.append(l).append('\n');
        return b.length() == 0 ? "—" : b.toString();
    }
}
