-- T16 additive change for an existing schema upgraded through 004.
-- Execute once after backup. Legacy skeletons retain NULL context and command acknowledgements.
ALTER TABLE interview_sessions
    ADD COLUMN agent_session_id VARCHAR(36) NULL,
    ADD COLUMN source_snapshot JSON NULL,
    ADD INDEX ix_interview_sessions_agent_session_id (agent_session_id),
    ADD CONSTRAINT fk_interview_agent_session FOREIGN KEY (agent_session_id) REFERENCES agent_sessions(id);
ALTER TABLE interview_turns ADD COLUMN question_context JSON NULL;
ALTER TABLE interview_commands
    ADD COLUMN request_json JSON NULL,
    ADD COLUMN ack_json JSON NULL;
