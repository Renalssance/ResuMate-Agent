-- T12 additive change for an existing schema upgraded through 002.
-- Execute once, after backup. Unknown capacity stays NULL.
ALTER TABLE user_llm_settings ADD COLUMN context_window_tokens INTEGER NULL;
ALTER TABLE agent_sessions
    ADD COLUMN context_invalidated_at DATETIME NULL,
    ADD COLUMN checkpoint_deleted_at DATETIME NULL;
CREATE TABLE business_memories (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind VARCHAR(18) NOT NULL,
    content LONGTEXT NOT NULL,
    source_ref JSON NOT NULL,
    confirmed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    deleted_at DATETIME NULL,
    CONSTRAINT business_memory_kind CHECK (kind IN ('preference', 'interview_feedback')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX ix_business_memories_user_id (user_id)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
