package fr.openbridge.companion;

import java.io.ByteArrayOutputStream;
import java.math.BigInteger;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * CPace on X25519 with SHA-512, byte-for-byte identical to src/fabric/cpace.py (see that file for the construction).
 * The 6-digit code shown on this screen is the password: nothing sent on the wire lets anyone test codes offline.
 * BigInteger arithmetic: a pairing runs a handful of scalar multiplications, once, while the owner watches.
 */
final class Cpace {
    static final BigInteger P = BigInteger.ONE.shiftLeft(255).subtract(BigInteger.valueOf(19));
    static final BigInteger A = BigInteger.valueOf(486662), A24 = BigInteger.valueOf(121665);
    static final BigInteger TWO = BigInteger.valueOf(2);
    static final byte[] DSI = "CPace255".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    static final byte[] DSI_ISK = "CPace255_ISK".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    static final int S_IN_BYTES = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private Cpace() {}

    static byte[] leb128(int n) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        do {
            int b = n & 0x7F;
            n >>>= 7;
            out.write(b | (n != 0 ? 0x80 : 0));
        } while (n != 0);
        return out.toByteArray();
    }

    static byte[] lv(byte[] data) { return cat(leb128(data.length), data); }

    static byte[] cat(byte[]... parts) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        for (byte[] p : parts) out.write(p, 0, p.length);
        return out.toByteArray();
    }

    static BigInteger decodeU(byte[] b) {
        if (b.length != 32) throw new SecurityException("a curve coordinate is 32 bytes");
        byte[] be = new byte[33];
        for (int i = 0; i < 32; i++) be[32 - i] = b[i];
        be[1] &= 0x7F;                               // mask the top bit (RFC 7748)
        return new BigInteger(be);
    }

    static byte[] encodeU(BigInteger u) {
        byte[] be = u.mod(P).toByteArray();
        byte[] out = new byte[32];
        for (int i = 0; i < 32 && i < be.length; i++) out[i] = be[be.length - 1 - i];
        return out;
    }

    static BigInteger clamp(byte[] k) {
        if (k.length != 32) throw new SecurityException("a scalar is 32 bytes");
        byte[] c = k.clone();
        c[0] &= (byte) 248;
        c[31] &= 127;
        c[31] |= 64;
        byte[] be = new byte[33];
        for (int i = 0; i < 32; i++) be[32 - i] = c[i];
        return new BigInteger(be);
    }

    /** RFC 7748 X25519 (Montgomery ladder). */
    static byte[] x25519(byte[] scalar, byte[] u) {
        BigInteger k = clamp(scalar), x1 = decodeU(u).mod(P);
        BigInteger x2 = BigInteger.ONE, z2 = BigInteger.ZERO, x3 = x1, z3 = BigInteger.ONE, t;
        int swap = 0;
        for (int i = 254; i >= 0; i--) {
            int kt = k.testBit(i) ? 1 : 0;
            swap ^= kt;
            if (swap == 1) { t = x2; x2 = x3; x3 = t; t = z2; z2 = z3; z3 = t; }
            swap = kt;
            BigInteger a = x2.add(z2).mod(P), b = x2.subtract(z2).mod(P);
            BigInteger aa = a.multiply(a).mod(P), bb = b.multiply(b).mod(P);
            BigInteger e = aa.subtract(bb).mod(P);
            BigInteger c = x3.add(z3).mod(P), d = x3.subtract(z3).mod(P);
            BigInteger da = d.multiply(a).mod(P), cb = c.multiply(b).mod(P);
            x3 = da.add(cb).pow(2).mod(P);
            z3 = x1.multiply(da.subtract(cb).pow(2)).mod(P);
            x2 = aa.multiply(bb).mod(P);
            z2 = e.multiply(aa.add(A24.multiply(e))).mod(P);
        }
        if (swap == 1) { x2 = x3; z2 = z3; }
        return encodeU(x2.multiply(z2.modPow(P.subtract(TWO), P)).mod(P));
    }

    static boolean isSquare(BigInteger x) {
        x = x.mod(P);
        return x.signum() == 0 || x.modPow(P.subtract(BigInteger.ONE).shiftRight(1), P).equals(BigInteger.ONE);
    }

    /** Map a field element to the u-coordinate of a point of Curve25519 (Z = 2). */
    static BigInteger elligator2(BigInteger r) {
        r = r.mod(P);
        BigInteger t = BigInteger.ONE.add(TWO.multiply(r).multiply(r)).mod(P);
        BigInteger x1 = t.signum() == 0 ? A.negate().mod(P) : A.negate().multiply(t.modPow(P.subtract(TWO), P)).mod(P);
        BigInteger gx1 = x1.pow(3).add(A.multiply(x1).multiply(x1)).add(x1).mod(P);
        return isSquare(gx1) ? x1 : x1.negate().subtract(A).mod(P);
    }

    static byte[] sha512(byte[] data) throws Exception { return MessageDigest.getInstance("SHA-512").digest(data); }

    static byte[] generator(byte[] prs, byte[] ci, byte[] sid) throws Exception {
        int zpad = Math.max(0, S_IN_BYTES - 1 - lv(prs).length - lv(DSI).length);
        byte[] h = sha512(cat(lv(DSI), lv(prs), lv(new byte[zpad]), lv(ci), lv(sid)));
        byte[] h32 = new byte[32];
        System.arraycopy(h, 0, h32, 0, 32);
        return encodeU(elligator2(decodeU(h32)));
    }

    static byte[] randomScalar() { byte[] y = new byte[32]; RANDOM.nextBytes(y); return y; }

    /** Intermediate session key; ya/yb are the initiator's (PC) / responder's (this relay) shares, in that order. */
    static byte[] isk(byte[] y, byte[] yOther, byte[] sid, byte[] ya, byte[] yb) throws Exception {
        byte[] k = x25519(y, yOther);
        if (MessageDigest.isEqual(k, new byte[32])) throw new SecurityException("invalid peer share");
        return sha512(cat(lv(DSI_ISK), lv(sid), lv(k), lv(ya), lv(new byte[0]), lv(yb), lv(new byte[0])));
    }
}
