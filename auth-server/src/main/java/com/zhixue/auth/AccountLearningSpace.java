package com.zhixue.auth;

import java.security.SecureRandom;
import java.util.HexFormat;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
@ConditionalOnProperty(name="auth.learning-space.enabled", havingValue="true")
public class AccountLearningSpace {
    public record Binding(String spaceId, AuthService.User user) {}

    private final AuthService auth;
    private final JdbcTemplate sql;
    private final SecureRandom random = new SecureRandom();

    public AccountLearningSpace(AuthService auth, JdbcTemplate sql) {
        this.auth = auth;
        this.sql = sql;
    }

    @Transactional(isolation=Isolation.READ_COMMITTED)
    public Binding resolve(String authorization) {
        AuthService.User user = auth.current(authorization);
        String userId = user.id();
        // Serialize the first allocation on the existing account row, including across processes.
        sql.queryForObject("SELECT id FROM auth_user WHERE id=? FOR UPDATE", String.class, userId);
        var existing = sql.queryForList(
                "SELECT space_id FROM account_learning_space WHERE user_id=?", String.class, userId);
        if (!existing.isEmpty()) return new Binding(existing.get(0), user);

        byte[] bytes = new byte[24];
        random.nextBytes(bytes);
        String spaceId = HexFormat.of().formatHex(bytes);
        sql.update("INSERT INTO account_learning_space(user_id,space_id,created_at) VALUES(?,?,?)",
                userId, spaceId, System.currentTimeMillis());
        return new Binding(spaceId, user);
    }
}
