package com.zhixue.auth;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/** Salted PBKDF2-HMAC-SHA256. Passwords never enter the session table or logs. */
final class PasswordHash {
    private static final int ITERATIONS = 600_000;
    private static final SecureRandom RANDOM = new SecureRandom();
    static String create(String password) {
        byte[] salt = new byte[16]; RANDOM.nextBytes(salt);
        return ITERATIONS + "$" + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(derive(password, salt, ITERATIONS));
    }
    static boolean matches(String password, String stored) {
        String[] fields = stored.split("\\$");
        return MessageDigest.isEqual(Base64.getDecoder().decode(fields[2]),
                derive(password, Base64.getDecoder().decode(fields[1]), Integer.parseInt(fields[0])));
    }
    private static byte[] derive(String password, byte[] salt, int iterations) {
        char[] chars = password.toCharArray();
        PBEKeySpec spec = new PBEKeySpec(chars, salt, iterations, 256);
        try { return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded(); }
        catch (Exception e) { throw new IllegalStateException("Password hashing unavailable", e); }
        finally { spec.clearPassword(); Arrays.fill(chars, '\0'); }
    }
}
