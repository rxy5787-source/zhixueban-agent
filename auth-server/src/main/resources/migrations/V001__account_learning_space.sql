CREATE TABLE IF NOT EXISTS account_learning_space (
    user_id VARCHAR(36) PRIMARY KEY REFERENCES auth_user(id),
    space_id VARCHAR(48) NOT NULL UNIQUE CHECK (CHAR_LENGTH(space_id) = 48),
    created_at BIGINT NOT NULL
);
