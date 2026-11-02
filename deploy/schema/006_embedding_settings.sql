CREATE TABLE IF NOT EXISTS embedding_settings (
    id INTEGER PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'openai',
    api_key TEXT NOT NULL,
    base_url VARCHAR(1024) NOT NULL DEFAULT '',
    model VARCHAR(255) NOT NULL DEFAULT ''
);
