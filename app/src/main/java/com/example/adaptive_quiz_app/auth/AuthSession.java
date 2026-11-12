package com.example.adaptive_quiz_app.auth;

/** The bearer token is only held in memory or Keystore-encrypted preferences. */
public final class AuthSession {
    public final String token, userId, username;
    public final long expiresAt;
    public AuthSession(String token, String userId, String username, long expiresAt) {
        this.token=token;this.userId=userId;this.username=username;this.expiresAt=expiresAt;
    }
    /** A cached identity only opens local data while its saved server lifetime is valid. */
    public boolean usableAt(long now) {
        return token!=null&&!token.isEmpty()&&userId!=null&&!userId.isEmpty()
                &&username!=null&&!username.isEmpty()&&expiresAt>now;
    }
}
