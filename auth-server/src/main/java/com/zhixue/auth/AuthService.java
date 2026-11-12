package com.zhixue.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
    public record User(String id, String username) { }
    public record Login(String token, long expiresAt, User user) { }
    private final JdbcTemplate sql;
    private final long sessionMillis;
    private final String dummyHash = PasswordHash.create("unknown-account-dummy-password");
    private final SecureRandom random = new SecureRandom();
    public AuthService(JdbcTemplate sql, @Value("${auth.session-seconds}") long seconds) {
        if (seconds < 60 || seconds > 2_592_000) throw new IllegalArgumentException("Session lifetime outside supported range");
        this.sql = sql; sessionMillis = seconds * 1000;
    }
    @Transactional
    public Login register(String username, String password) {
        String normalized = normalize(username);
        String id = UUID.randomUUID().toString();
        try { sql.update("INSERT INTO auth_user(id,username,password_hash,created_at) VALUES(?,?,?,?)",
                id, normalized, PasswordHash.create(password), System.currentTimeMillis()); }
        catch (DuplicateKeyException e) { throw new ResponseStatusException(HttpStatus.CONFLICT, "该账号已被注册"); }
        return issue(new User(id, normalized));
    }
    @Transactional
    public Login login(String username, String password) {
        var rows = sql.queryForList("SELECT id,username,password_hash FROM auth_user WHERE username=?", normalize(username));
        String hash = rows.isEmpty() ? dummyHash : (String)rows.get(0).get("PASSWORD_HASH");
        // Column labels are normalized by JdbcTemplate's case-insensitive map on both H2 and PostgreSQL.
        if (!PasswordHash.matches(password, hash) || rows.isEmpty())
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "账号或密码错误");
        var row = rows.get(0);
        return issue(new User((String)row.get("ID"), (String)row.get("USERNAME")));
    }
    private Login issue(User user) {
        byte[] bytes = new byte[32]; random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        long expiry = System.currentTimeMillis() + sessionMillis;
        sql.update("DELETE FROM auth_session WHERE expires_at<=?", System.currentTimeMillis());
        sql.update("INSERT INTO auth_session(token_hash,user_id,expires_at) VALUES(?,?,?)", digest(token), user.id, expiry);
        return new Login(token, expiry, user);
    }
    public User current(String authorization) {
        String token = bearer(authorization);
        var users = sql.query("SELECT u.id,u.username FROM auth_user u JOIN auth_session s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?",
                (rs, n) -> new User(rs.getString("id"), rs.getString("username")), digest(token), System.currentTimeMillis());
        if (users.isEmpty()) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "登录已失效，请重新登录");
        return users.get(0);
    }
    /** Extend an existing session; an expired or deleted row is never recreated. */
    @Transactional
    public Login renew(String authorization) {
        String token=bearer(authorization);
        long now=System.currentTimeMillis(),expiry=now+sessionMillis;
        int updated=sql.update("UPDATE auth_session SET expires_at=GREATEST(expires_at,?) WHERE token_hash=? AND expires_at>?",
                expiry,digest(token),now);
        if(updated!=1)throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"登录已失效，请重新登录");
        User user=current(authorization);
        long savedExpiry=sql.queryForObject("SELECT expires_at FROM auth_session WHERE token_hash=?",Long.class,digest(token));
        return new Login(token,savedExpiry,user);
    }
    public void logout(String authorization) { sql.update("DELETE FROM auth_session WHERE token_hash=?", digest(bearer(authorization))); }
    private static String normalize(String username) { return username.toLowerCase(Locale.ROOT); }
    private static String bearer(String header) {
        if (header == null || !header.matches("Bearer [A-Za-z0-9_-]{43}"))
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "请先登录");
        return header.substring(7);
    }
    static String digest(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
}
