-- Insurance AI Database Schema
-- PostgreSQL 15+
-- Apply with: psql -h localhost -p 5433 -U insurance_ai -d insurance_ai -f database/schema.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(255),
    is_active     BOOLEAN      DEFAULT TRUE,
    is_verified   BOOLEAN      DEFAULT FALSE,
    created_at    TIMESTAMP    DEFAULT NOW(),
    updated_at    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── Workspaces ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workspaces (
    id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID         REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workspaces_user_id ON workspaces(user_id);

-- ── Policies ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS policies (
    id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id  UUID         REFERENCES workspaces(id) ON DELETE CASCADE,
    policy_number VARCHAR(100) UNIQUE,
    policy_type   VARCHAR(50),
    policy_data   JSONB,
    status        VARCHAR(20)  DEFAULT 'active',
    created_at    TIMESTAMP    DEFAULT NOW(),
    updated_at    TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_policies_workspace_id  ON policies(workspace_id);
CREATE INDEX IF NOT EXISTS idx_policies_policy_number ON policies(policy_number);

-- ── Chat History ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_history (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID         REFERENCES workspaces(id) ON DELETE CASCADE,
    session_id   VARCHAR(100),
    messages     JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at   TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_workspace_id ON chat_history(workspace_id);
CREATE INDEX IF NOT EXISTS idx_chat_session      ON chat_history(workspace_id, session_id);
CREATE INDEX IF NOT EXISTS idx_chat_created_at   ON chat_history(created_at);

-- ── Uploads ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS uploads (
    id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id      UUID         REFERENCES workspaces(id) ON DELETE CASCADE,
    filename          VARCHAR(255),
    original_filename VARCHAR(255),
    file_path         VARCHAR(500),
    file_type         VARCHAR(50),
    file_size         BIGINT,
    extraction_status VARCHAR(20)  DEFAULT 'pending',
    extracted_text    TEXT,
    chunk_count       INT          DEFAULT 0,
    indexed_at        TIMESTAMP,
    error_message     TEXT,
    uploaded_at       TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_uploads_workspace_id ON uploads(workspace_id);

-- ── Password Reset Tokens ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID         REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP    NOT NULL,
    used_at    TIMESTAMP,
    created_at TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_prt_user_id    ON password_reset_tokens(user_id);

-- ── API Keys ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID         REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    key_prefix   VARCHAR(20)  NOT NULL,
    key_hash     VARCHAR(255) UNIQUE NOT NULL,
    is_active    BOOLEAN      DEFAULT TRUE,
    created_at   TIMESTAMP    DEFAULT NOW(),
    last_used_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id  ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);

-- ── updated_at trigger ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

DO $$ BEGIN
    CREATE TRIGGER update_users_updated_at      BEFORE UPDATE ON users      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER update_workspaces_updated_at BEFORE UPDATE ON workspaces FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE TRIGGER update_policies_updated_at   BEFORE UPDATE ON policies   FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

SELECT 'Schema applied successfully' AS status;
