package com.zhixue.auth;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ConditionalOnProperty(name="auth.learning-space.enabled", havingValue="true")
public class AccountLearningSpaceController {
    private final AccountLearningSpace spaces;

    public AccountLearningSpaceController(AccountLearningSpace spaces) {
        this.spaces = spaces;
    }

    @PostMapping("/api/auth/learning-space")
    public AccountLearningSpace.Binding resolve(
            @RequestHeader(value="Authorization", required=false) String authorization) {
        return spaces.resolve(authorization);
    }
}
