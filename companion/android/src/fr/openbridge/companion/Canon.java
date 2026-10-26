package fr.openbridge.companion;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/** Canonical JSON identical to Python json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True). */
final class Canon {
    private Canon() {}

    static String of(Object v) {
        StringBuilder b = new StringBuilder();
        write(b, v);
        return b.toString();
    }

    private static void write(StringBuilder b, Object v) {
        if (v == null || v == JSONObject.NULL) { b.append("null"); return; }
        if (v instanceof Boolean) { b.append(((Boolean) v) ? "true" : "false"); return; }
        if (v instanceof Integer || v instanceof Long || v instanceof Short) { b.append(v.toString()); return; }
        if (v instanceof Number) {
            double d = ((Number) v).doubleValue();
            if (d == Math.rint(d) && Math.abs(d) < 1e15) { b.append((long) d); return; }
            throw new IllegalArgumentException("Non-integer numbers are not used by the protocol");
        }
        if (v instanceof String) { string(b, (String) v); return; }
        if (v instanceof JSONObject) {
            JSONObject o = (JSONObject) v;
            List<String> keys = new ArrayList<>();
            for (Iterator<String> it = o.keys(); it.hasNext();) keys.add(it.next());
            Collections.sort(keys);
            b.append('{');
            for (int i = 0; i < keys.size(); i++) {
                if (i > 0) b.append(',');
                string(b, keys.get(i)); b.append(':'); write(b, o.opt(keys.get(i)));
            }
            b.append('}');
            return;
        }
        if (v instanceof JSONArray) {
            JSONArray a = (JSONArray) v;
            b.append('[');
            for (int i = 0; i < a.length(); i++) { if (i > 0) b.append(','); write(b, a.opt(i)); }
            b.append(']');
            return;
        }
        throw new IllegalArgumentException("Unsupported JSON value");
    }

    private static void string(StringBuilder b, String s) {
        b.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                case '\b': b.append("\\b"); break;
                case '\f': b.append("\\f"); break;
                default:
                    if (c < 0x20 || c > 0x7e && c != 0x7f) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        b.append('"');
    }
}
