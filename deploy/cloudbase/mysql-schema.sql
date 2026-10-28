-- Initial ResuMate schema for existing CloudBase MySQL.
-- Run only after inspecting target tables; no IF NOT EXISTS, ALTER or DROP.

CREATE TABLE document_embedding_chunks (
	user_id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	document_type VARCHAR(20) NOT NULL, 
	chunk_id VARCHAR(255) NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	page_number INTEGER NOT NULL, 
	section TEXT NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	embedding JSON NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (user_id, document_id, document_type, chunk_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE embedding_contracts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	provider VARCHAR(255) NOT NULL, 
	model VARCHAR(1024) NOT NULL, 
	dimension INTEGER NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id),
	INDEX ix_users_id (id),
	UNIQUE INDEX ix_users_username (username)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE chat_sessions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	session_id VARCHAR(120) NOT NULL, 
	metadata_json JSON NOT NULL, 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_session UNIQUE (user_id, session_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	INDEX ix_chat_sessions_id (id),
	INDEX ix_chat_sessions_session_id (session_id),
	INDEX ix_chat_sessions_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE job_descriptions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	company VARCHAR(255) NOT NULL, 
	filename VARCHAR(255) NOT NULL DEFAULT '', 
	file_path VARCHAR(1024) NOT NULL DEFAULT '', 
	content_hash VARCHAR(64) NOT NULL DEFAULT '', 
	document_size INTEGER NOT NULL DEFAULT '0', 
	parse_status VARCHAR(40) NOT NULL DEFAULT 'pending', 
	raw_text LONGTEXT NOT NULL, 
	structured_data JSON, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	INDEX ix_job_descriptions_content_hash (content_hash),
	INDEX ix_job_descriptions_parse_status (parse_status),
	INDEX ix_job_descriptions_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE llm_usage_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	task VARCHAR(120) NOT NULL, 
	model VARCHAR(255) NOT NULL, 
	base_url VARCHAR(1024) NOT NULL, 
	prompt_tokens INTEGER NOT NULL, 
	completion_tokens INTEGER NOT NULL, 
	total_tokens INTEGER NOT NULL, 
	success BOOL NOT NULL, 
	error_type VARCHAR(120) NOT NULL, 
	elapsed_ms INTEGER NOT NULL, 
	called_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	INDEX ix_llm_usage_events_called_at (called_at),
	INDEX ix_llm_usage_events_success (success),
	INDEX ix_llm_usage_events_task (task),
	INDEX ix_llm_usage_events_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE resumes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	file_path VARCHAR(1024) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL DEFAULT '', 
	document_size INTEGER NOT NULL DEFAULT '0', 
	parse_status VARCHAR(40) NOT NULL DEFAULT 'pending', 
	raw_text LONGTEXT NOT NULL, 
	structured_data JSON, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	INDEX ix_resumes_content_hash (content_hash),
	INDEX ix_resumes_parse_status (parse_status),
	INDEX ix_resumes_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE user_llm_settings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	api_key TEXT NOT NULL, 
	base_url VARCHAR(1024) NOT NULL, 
	model VARCHAR(255) NOT NULL, 
	max_tokens INTEGER, 
	request_timeout_seconds FLOAT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	UNIQUE INDEX ix_user_llm_settings_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE analysis_jobs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	jd_id INTEGER, 
	title VARCHAR(255) NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	summary TEXT NOT NULL, 
	config_json JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL,
	INDEX ix_analysis_jobs_jd_id (jd_id),
	INDEX ix_analysis_jobs_status (status),
	INDEX ix_analysis_jobs_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE chat_messages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	session_ref_id INTEGER NOT NULL, 
	message_type VARCHAR(20) NOT NULL, 
	content LONGTEXT NOT NULL, 
	timestamp DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_ref_id) REFERENCES chat_sessions (id) ON DELETE CASCADE,
	INDEX ix_chat_messages_id (id),
	INDEX ix_chat_messages_session_ref_id (session_ref_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE job_applications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	resume_id INTEGER, 
	company VARCHAR(255) NOT NULL, 
	position VARCHAR(255) NOT NULL, 
	applied_date DATE NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	job_url VARCHAR(1024) NOT NULL DEFAULT '', 
	source VARCHAR(120) NOT NULL DEFAULT '', 
	notes TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE SET NULL,
	INDEX ix_job_applications_applied_date (applied_date),
	INDEX ix_job_applications_resume_id (resume_id),
	INDEX ix_job_applications_status (status),
	INDEX ix_job_applications_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE analysis_candidates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	job_id INTEGER NOT NULL, 
	resume_id INTEGER NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	note TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_analysis_job_resume UNIQUE (job_id, resume_id), 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE CASCADE,
	INDEX ix_analysis_candidates_job_id (job_id),
	INDEX ix_analysis_candidates_resume_id (resume_id),
	INDEX ix_analysis_candidates_status (status)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE job_application_status_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	application_id INTEGER NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	changed_at DATETIME NOT NULL, 
	note TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(application_id) REFERENCES job_applications (id) ON DELETE CASCADE,
	INDEX ix_job_application_status_events_application_id (application_id),
	INDEX ix_job_application_status_events_changed_at (changed_at),
	INDEX ix_job_application_status_events_status (status)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE follow_up_question_sets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	job_id INTEGER NOT NULL, 
	candidate_id INTEGER NOT NULL, 
	resume_id INTEGER NOT NULL, 
	jd_id INTEGER, 
	questions JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_followup_job_candidate UNIQUE (job_id, candidate_id), 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_id) REFERENCES analysis_candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL,
	INDEX ix_follow_up_question_sets_candidate_id (candidate_id),
	INDEX ix_follow_up_question_sets_jd_id (jd_id),
	INDEX ix_follow_up_question_sets_job_id (job_id),
	INDEX ix_follow_up_question_sets_resume_id (resume_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE interview_question_sets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	job_id INTEGER NOT NULL, 
	candidate_id INTEGER NOT NULL, 
	resume_id INTEGER NOT NULL, 
	jd_id INTEGER, 
	questions JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_question_job_candidate UNIQUE (job_id, candidate_id), 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_id) REFERENCES analysis_candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL,
	INDEX ix_interview_question_sets_candidate_id (candidate_id),
	INDEX ix_interview_question_sets_jd_id (jd_id),
	INDEX ix_interview_question_sets_job_id (job_id),
	INDEX ix_interview_question_sets_resume_id (resume_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE job_application_schedules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	application_id INTEGER NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	starts_at DATETIME NOT NULL, 
	ends_at DATETIME NOT NULL, 
	note TEXT NOT NULL, 
	completed_event_id INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	FOREIGN KEY(application_id) REFERENCES job_applications (id) ON DELETE CASCADE, 
	FOREIGN KEY(completed_event_id) REFERENCES job_application_status_events (id) ON DELETE SET NULL,
	INDEX ix_job_application_schedules_application_id (application_id),
	INDEX ix_job_application_schedules_completed_event_id (completed_event_id),
	INDEX ix_job_application_schedules_ends_at (ends_at),
	INDEX ix_job_application_schedules_starts_at (starts_at),
	INDEX ix_job_application_schedules_status (status)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE match_results (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	job_id INTEGER NOT NULL, 
	candidate_id INTEGER NOT NULL, 
	resume_id INTEGER NOT NULL, 
	jd_id INTEGER, 
	overall_score FLOAT NOT NULL, 
	recommendation VARCHAR(40) NOT NULL, 
	reason TEXT NOT NULL, 
	dimension_scores JSON NOT NULL, 
	matched_skills JSON NOT NULL, 
	missing_skills JSON NOT NULL, 
	strengths JSON NOT NULL, 
	gaps JSON NOT NULL, 
	report_json JSON NOT NULL DEFAULT ('{}'), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	_openid VARCHAR(64) NOT NULL DEFAULT '', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_match_job_candidate UNIQUE (job_id, candidate_id), 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_id) REFERENCES analysis_candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES resumes (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES job_descriptions (id) ON DELETE SET NULL,
	INDEX ix_match_results_candidate_id (candidate_id),
	INDEX ix_match_results_jd_id (jd_id),
	INDEX ix_match_results_job_id (job_id),
	INDEX ix_match_results_recommendation (recommendation),
	INDEX ix_match_results_resume_id (resume_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;
