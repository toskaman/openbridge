package fr.openbridge.companion;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Cross-language check: the Companion's Aead must reproduce tests/fabric/fixtures/aead1_vector.json exactly.
 *  Run (JDK, android.jar on the classpath for compile only):
 *  javac -cp android.jar -d out companion/android/src/fr/openbridge/companion/Aead.java dev/aead_vector_check/AeadVectorCheck.java
 *  java -cp out;android.jar fr.openbridge.companion.AeadVectorCheck tests/fabric/fixtures/aead1_vector.json */
public final class AeadVectorCheck {
    static String field(String json, String key, int from) {
        Matcher m = Pattern.compile("\"" + key + "\":\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").matcher(json);
        if (!m.find(from)) throw new IllegalStateException("missing " + key);
        return m.group(1);
    }

    public static void main(String[] a) throws Exception {
        String j = new String(Files.readAllBytes(Paths.get(a[0])), "UTF-8");
        byte[] key = Aead.unhex(field(j, "key_hex", 0)), nonce = Aead.unhex(field(j, "nonce_hex", 0));
        String aad = field(j, "aad", 0), pt = field(j, "plaintext", 0).replace("\\\"", "\"");
        int env = j.indexOf("\"envelope\"");
        byte[] ct = Aead.stream(Aead.kenc(key), nonce, pt.getBytes("UTF-8"));
        String c = Base64.getEncoder().encodeToString(ct), t = Aead.hex(Aead.tag(Aead.kmac(key), aad, nonce, ct));
        boolean ok1 = c.equals(field(j, "c", env)) && t.equals(field(j, "t", env));
        int v = j.indexOf("\"voice\"");
        String vaad = field(j, "aad", v); byte[] vpt = Aead.unhex(field(j, "plaintext_hex", v));
        int venv = j.indexOf("\"envelope\"", v);
        byte[] vct = Aead.stream(Aead.kenc(key), nonce, vpt);
        boolean ok2 = Base64.getEncoder().encodeToString(vct).equals(field(j, "c", venv)) && Aead.hex(Aead.tag(Aead.kmac(key), vaad, nonce, vct)).equals(field(j, "t", venv));
        System.out.println("command vector " + (ok1 ? "MATCH" : "MISMATCH c=" + c + " t=" + t));
        System.out.println("voice vector " + (ok2 ? "MATCH" : "MISMATCH"));
        if (!(ok1 && ok2)) System.exit(1);
    }
}
