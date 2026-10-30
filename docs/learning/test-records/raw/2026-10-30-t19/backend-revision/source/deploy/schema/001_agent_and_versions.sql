-- T02 additive migration for an existing ResuMate MySQL schema.
-- Back up first and execute ONCE. MySQL DDL commits implicitly.
-- On failure inspect applied statements before continuing. No DROP or DELETE.
-- This script preserves existing business rows. See deploy/schema/README.md.

CREATE TABLE agent_sessions (
	id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	purpose VARCHAR(80) NOT NULL, 
	active_run_id VARCHAR(36), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_agent_session_owner UNIQUE (id, user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE INDEX ix_agent_sessions_user_id ON agent_sessions (user_id);

CREATE TABLE agent_runs (
	id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	request_id VARCHAR(100) NOT NULL, 
	kind VARCHAR(80) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	input_json JSON NOT NULL, 
	input_versions JSON NOT NULL, 
	attempt INTEGER NOT NULL, 
	execution_epoch INTEGER NOT NULL, 
	heartbeat_at DATETIME, 
	cancel_requested_at DATETIME, 
	error_code VARCHAR(100), 
	output_refs JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_agent_run_request UNIQUE (user_id, request_id), 
	FOREIGN KEY(session_id, user_id) REFERENCES agent_sessions (id, user_id) ON DELETE CASCADE, 
	CONSTRAINT ck_agent_run_attempt CHECK (attempt >= 1 AND execution_epoch >= 0), 
	CONSTRAINT run_status CHECK (status IN ('queued', 'running', 'waiting_input', 'waiting_approval', 'succeeded', 'failed', 'cancelled'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE INDEX ix_agent_runs_session_id ON agent_runs (session_id);

CREATE INDEX ix_agent_runs_status ON agent_runs (status);

CREATE INDEX ix_agent_runs_user_id ON agent_runs (user_id);

CREATE TABLE profile_facts (
	id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	fact_key VARCHAR(100) NOT NULL, 
	kind VARCHAR(80) NOT NULL, 
	content JSON NOT NULL, 
	source_document_id INTEGER, 
	revision INTEGER NOT NULL, 
	confirmed_at DATETIME, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_profile_fact_revision UNIQUE (user_id, fact_key, revision), 
	CONSTRAINT ck_profile_fact_revision CHECK (revision > 0), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(source_document_id) REFERENCES resumes (id) ON DELETE SET NULL
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE INDEX ix_profile_facts_user_id ON profile_facts (user_id);

CREATE TABLE agent_actions (
	id VARCHAR(36) NOT NULL, 
	run_id VARCHAR(36) NOT NULL, 
	interrupt_id VARCHAR(100) NOT NULL, 
	kind VARCHAR(8) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	response JSON, 
	answered_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_agent_action_interrupt UNIQUE (run_id, interrupt_id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE CASCADE, 
	CONSTRAINT action_kind CHECK (kind IN ('input', 'approval')), 
	CONSTRAINT action_status CHECK (status IN ('pending', 'answered'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE agent_run_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	run_id VARCHAR(36) NOT NULL, 
	seq INTEGER NOT NULL, 
	type VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_agent_run_event_seq UNIQUE (run_id, seq), 
	CONSTRAINT ck_agent_run_event_seq CHECK (seq > 0), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE CASCADE
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE resume_versions (
	id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	run_id VARCHAR(36), 
	resume_id INTEGER, 
	jd_id INTEGER, 
	parent_version_id VARCHAR(36), 
	revision INTEGER NOT NULL, 
	structured_content JSON NOT NULL, 
	fact_refs JSON NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_resume_version_revision CHECK (revision > 0), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE SET NULL, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE SET NULL, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL, 
	FOREIGN KEY(parent_version_id) REFERENCES resume_versions (id) ON DELETE SET NULL, 
	CONSTRAINT version_status CHECK (status IN ('draft', 'confirmed'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE INDEX ix_resume_versions_jd_id ON resume_versions (jd_id);

CREATE INDEX ix_resume_versions_resume_id ON resume_versions (resume_id);

CREATE INDEX ix_resume_versions_run_id ON resume_versions (run_id);

CREATE INDEX ix_resume_versions_user_id ON resume_versions (user_id);

CREATE TABLE tool_operations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	run_id VARCHAR(36) NOT NULL, 
	operation_key VARCHAR(160) NOT NULL, 
	tool_name VARCHAR(100) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	result_ref VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tool_operation_key UNIQUE (run_id, operation_key), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id) ON DELETE CASCADE, 
	CONSTRAINT tool_operation_status CHECK (status IN ('pending', 'succeeded', 'failed'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE interview_sessions (
	id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	application_id INTEGER, 
	jd_id INTEGER, 
	resume_version_id VARCHAR(36) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(application_id) REFERENCES job_applications (id) ON DELETE SET NULL, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL, 
	FOREIGN KEY(resume_version_id) REFERENCES resume_versions (id), 
	CONSTRAINT interview_status CHECK (status IN ('active', 'finished'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE INDEX ix_interview_sessions_user_id ON interview_sessions (user_id);

CREATE TABLE interview_commands (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	interview_id VARCHAR(36) NOT NULL, 
	user_id INTEGER NOT NULL, 
	client_message_id VARCHAR(100) NOT NULL, 
	type VARCHAR(40) NOT NULL, 
	result_ref VARCHAR(255), 
	status VARCHAR(9) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_interview_command UNIQUE (interview_id, client_message_id), 
	FOREIGN KEY(interview_id) REFERENCES interview_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT interview_command_status CHECK (status IN ('accepted', 'succeeded', 'failed'))
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE interview_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	interview_id VARCHAR(36) NOT NULL, 
	seq INTEGER NOT NULL, 
	type VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_interview_event_seq UNIQUE (interview_id, seq), 
	CONSTRAINT ck_interview_event_seq CHECK (seq > 0), 
	FOREIGN KEY(interview_id) REFERENCES interview_sessions (id) ON DELETE CASCADE
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE interview_turns (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	interview_id VARCHAR(36) NOT NULL, 
	turn_index INTEGER NOT NULL, 
	question LONGTEXT NOT NULL, 
	answer LONGTEXT, 
	feedback JSON, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_interview_turn UNIQUE (interview_id, turn_index), 
	CONSTRAINT ck_interview_turn_index CHECK (turn_index >= 0), 
	FOREIGN KEY(interview_id) REFERENCES interview_sessions (id) ON DELETE CASCADE
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE job_descriptions
  ADD COLUMN source_url VARCHAR(1024) NULL,
  ADD COLUMN source_site VARCHAR(100) NULL,
  ADD COLUMN source_job_id VARCHAR(255) NULL,
  ADD COLUMN captured_at DATETIME NULL,
  ADD COLUMN status VARCHAR(40) NOT NULL DEFAULT 'saved',
  ADD CONSTRAINT uq_job_source UNIQUE (user_id, source_site, source_job_id);

ALTER TABLE job_applications
  ADD COLUMN jd_id INTEGER NULL,
  ADD COLUMN resume_version_id VARCHAR(36) COLLATE utf8mb4_bin NULL,
  ADD COLUMN submitted_snapshot JSON NULL,
  ADD CONSTRAINT fk_application_jd FOREIGN KEY (jd_id) REFERENCES job_descriptions(id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_application_version FOREIGN KEY (resume_version_id) REFERENCES resume_versions(id) ON DELETE SET NULL,
  ADD INDEX ix_job_applications_jd_id (jd_id),
  ADD INDEX ix_job_applications_resume_version_id (resume_version_id);
