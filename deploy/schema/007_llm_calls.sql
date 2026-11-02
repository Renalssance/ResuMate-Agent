-- Local SQLite creates this table through Base.metadata.create_all.
-- Apply once to existing MySQL installations before starting the new backend.
CREATE TABLE IF NOT EXISTS llm_calls (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  task VARCHAR(120) NOT NULL,
  model VARCHAR(255) NOT NULL DEFAULT '',
  base_url VARCHAR(1024) NOT NULL DEFAULT '',
  attempt INT NOT NULL DEFAULT 1,
  status VARCHAR(24) NOT NULL DEFAULT 'running',
  request_json JSON NOT NULL,
  output_json JSON NULL,
  usage_json JSON NULL,
  error LONGTEXT NOT NULL,
  elapsed_ms INT NOT NULL DEFAULT 0,
  called_at DATETIME NOT NULL,
  INDEX ix_llm_calls_user_id (user_id),
  INDEX ix_llm_calls_called_at (called_at),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
