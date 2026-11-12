CREATE TABLE IF NOT EXISTS auth_user (
 id VARCHAR(36) PRIMARY KEY,
 username VARCHAR(32) NOT NULL UNIQUE,
 password_hash VARCHAR(256) NOT NULL,
 created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_session (
 token_hash VARCHAR(64) PRIMARY KEY,
 user_id VARCHAR(36) NOT NULL REFERENCES auth_user(id),
 expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_session_expiry ON auth_session(expires_at);
