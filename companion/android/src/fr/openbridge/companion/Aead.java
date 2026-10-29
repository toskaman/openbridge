package fr.openbridge.companion;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.json.JSONObject;

/**
 * aead1: relay-channel confidentiality, byte-for-byte identical to src/fabric/aead.py.
 * Encrypt-then-MAC: HMAC-SHA256 counter-mode keystream XOR plaintext, HMAC-SHA256 tag over (aad, nonce, ciphertext),
 * with encryption and MAC subkeys derived from the pairing key. The tag is verified before anything is decrypted.
 */
final class Aead {
    static final String VERSION = "aead1";
    static final int NONCE = 16, MAX = 1 << 20;
    private static final SecureRandom RANDOM = new SecureRandom();

    private Aead() {}

    static byte[] mac(byte[] key, byte[]... parts) throws Exception {
        Mac m = Mac.getInstance("HmacSHA256");
        m.init(new SecretKeySpec(key, "HmacSHA256"));
        for (byte[] p : parts) m.update(p);
        return m.doFinal();
    }

    static byte[] kenc(byte[] key) throws Exception { return mac(key, "obr-aead1|enc".getBytes(StandardCharsets.US_ASCII)); }
    static byte[] kmac(byte[] key) throws Exception { return mac(key, "obr-aead1|mac".getBytes(StandardCharsets.US_ASCII)); }

    static byte[] stream(byte[] kenc, byte[] nonce, byte[] data) throws Exception {
        byte[] out = new byte[data.length];
        Mac m = Mac.getInstance("HmacSHA256");
        m.init(new SecretKeySpec(kenc, "HmacSHA256"));
        for (int i = 0, block = 0; i < data.length; i += 32, block++) {
            m.update(nonce);
            m.update(new byte[]{(byte) (block >>> 24), (byte) (block >>> 16), (byte) (block >>> 8), (byte) block});
            byte[] ks = m.doFinal();
            for (int j = 0; j < 32 && i + j < data.length; j++) out[i + j] = (byte) (data[i + j] ^ ks[j]);
        }
        return out;
    }

    static byte[] tag(byte[] kmac, String aad, byte[] nonce, byte[] ct) throws Exception {
        byte[] a = aad.getBytes(StandardCharsets.UTF_8);
        byte[] len = {(byte) (a.length >>> 24), (byte) (a.length >>> 16), (byte) (a.length >>> 8), (byte) a.length};
        return mac(kmac, len, a, nonce, ct);
    }

    static JSONObject seal(byte[] key, String aad, byte[] pt, byte[] fixedNonce) throws Exception {
        if (pt.length > MAX) throw new SecurityException("too large");
        byte[] nonce = fixedNonce != null ? fixedNonce : new byte[NONCE];
        if (fixedNonce == null) RANDOM.nextBytes(nonce);
        byte[] ct = stream(kenc(key), nonce, pt);
        return new JSONObject().put("enc", VERSION).put("n", hex(nonce))
                .put("c", Base64.getEncoder().encodeToString(ct)).put("t", hex(tag(kmac(key), aad, nonce, ct)));
    }

    static byte[] open(byte[] key, String aad, JSONObject env) throws Exception {
        if (!VERSION.equals(env.optString("enc"))) throw new SecurityException("not aead1");
        byte[] nonce, ct;
        String t = env.optString("t");
        try { nonce = unhex(env.getString("n")); ct = Base64.getDecoder().decode(env.getString("c")); }
        catch (Exception e) { throw new SecurityException("malformed envelope"); }
        if (nonce.length != NONCE || t.length() != 64 || ct.length > MAX) throw new SecurityException("malformed envelope");
        if (!MessageDigest.isEqual(hex(tag(kmac(key), aad, nonce, ct)).getBytes(StandardCharsets.US_ASCII),
                t.getBytes(StandardCharsets.US_ASCII))) throw new SecurityException("authentication failed");
        return stream(kenc(key), nonce, ct);
    }

    /** Voice body: nonce(16) | tag(32) | ciphertext. */
    static byte[] sealVoice(byte[] key, String aad, byte[] pt) throws Exception {
        byte[] nonce = new byte[NONCE]; RANDOM.nextBytes(nonce);
        byte[] ct = stream(kenc(key), nonce, pt);
        byte[] tg = tag(kmac(key), aad, nonce, ct);
        byte[] out = new byte[NONCE + 32 + ct.length];
        System.arraycopy(nonce, 0, out, 0, NONCE); System.arraycopy(tg, 0, out, NONCE, 32); System.arraycopy(ct, 0, out, NONCE + 32, ct.length);
        return out;
    }

    static String aad(String relayId, String direction) { return VERSION + "|" + relayId + "|" + direction; }

    static String hex(byte[] b) { StringBuilder s = new StringBuilder(); for (byte x : b) s.append(String.format("%02x", x)); return s.toString(); }
    static byte[] unhex(String s) {
        if (s.length() % 2 != 0) throw new IllegalArgumentException("odd hex");
        byte[] b = new byte[s.length() / 2]; for (int i = 0; i < b.length; i++) b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16); return b;
    }
}
