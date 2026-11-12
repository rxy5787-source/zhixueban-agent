package com.example.adaptive_quiz_app.auth;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

public final class SessionStore {
    private static final String KEY="zhixue.online.session.v1";
    private static final Object LOCK=new Object();
    private final SharedPreferences preferences;
    public SessionStore(Context context) { preferences=context.getSharedPreferences("online_auth",Context.MODE_PRIVATE); }
    public AuthSession load() { synchronized(LOCK) { return read(); } }
    private AuthSession read() {
        String encrypted=preferences.getString("token","");
        if(encrypted.isEmpty())return null;
        try {
            String value=decrypt(encrypted);
            if(value.startsWith("{")) {
                JSONObject session=new JSONObject(value);
                return new AuthSession(session.getString("token"),session.getString("userId"),
                        session.getString("username"),session.getLong("expiresAt"));
            }
            // Old versions encrypted only the token; migrate on the next confirmed renewal.
            return new AuthSession(value,preferences.getString("userId",""),
                    preferences.getString("username",""),preferences.getLong("expiresAt",0));
        } catch(Exception error) { clear();return null; }
    }
    public void save(AuthSession session) throws Exception { synchronized(LOCK) { write(session); } }
    private void write(AuthSession session) throws Exception {
        String value=new JSONObject().put("token",session.token).put("userId",session.userId)
                .put("username",session.username).put("expiresAt",session.expiresAt).toString();
        if(!preferences.edit().putString("token",encrypt(value)).remove("userId")
                .remove("username").remove("expiresAt").commit())
            throw new IllegalStateException("无法保存登录状态，请重试");
    }
    public boolean saveIfCurrent(AuthSession expected,AuthSession updated) throws Exception {
        synchronized(LOCK) {
            AuthSession current=read();
            if(!same(current,expected))return false;
            if(!same(updated,expected))throw new IllegalArgumentException("Session identity changed");
            write(new AuthSession(updated.token,updated.userId,updated.username,Math.max(current.expiresAt,updated.expiresAt)));
            return true;
        }
    }
    public boolean clearIfCurrent(AuthSession expected) {
        synchronized(LOCK) {
            if(!same(read(),expected))return false;
            clear();return true;
        }
    }
    private static boolean same(AuthSession a,AuthSession b) {
        return a!=null&&b!=null&&a.token.equals(b.token)&&a.userId.equals(b.userId);
    }
    public void clear() { synchronized(LOCK) { preferences.edit().remove("token").remove("userId").remove("username").remove("expiresAt").commit(); } }
    public void queueLogout(String token) throws Exception { synchronized(LOCK) {
        if(!preferences.edit().putString("pendingLogout",encrypt(token)).commit())throw new IllegalStateException("无法保存退出状态");
    } }
    public String pendingLogout() { synchronized(LOCK) {
        try { String value=preferences.getString("pendingLogout","");return value.isEmpty()?null:decrypt(value); }
        catch(Exception error) { clearPendingLogout();return null; }
    } }
    public void clearPendingLogout() { synchronized(LOCK) { preferences.edit().remove("pendingLogout").commit(); } }
    public void clearPendingLogout(String expected) { synchronized(LOCK) { if(expected.equals(pendingLogout()))clearPendingLogout(); } }
    private static SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(KEY))return (SecretKey)store.getKey(KEY,null);
        KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }
    private static String encrypt(String value) throws Exception {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        byte[] ciphertext=cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        byte[] data=new byte[12+ciphertext.length];System.arraycopy(cipher.getIV(),0,data,0,12);System.arraycopy(ciphertext,0,data,12,ciphertext.length);
        return Base64.encodeToString(data,Base64.NO_WRAP);
    }
    private static String decrypt(String value) throws Exception {
        byte[] data=Base64.decode(value,Base64.NO_WRAP);if(data.length<29)throw new IllegalArgumentException("Invalid session");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Arrays.copyOf(data,12)));
        return new String(cipher.doFinal(data,12,data.length-12),StandardCharsets.UTF_8);
    }
}
