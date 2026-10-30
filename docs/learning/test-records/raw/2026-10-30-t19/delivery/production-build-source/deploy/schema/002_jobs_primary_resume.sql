-- T08 additive change for a database already upgraded through 001.
-- Existing saved jobs retain NULL until the user selects a primary resume.
ALTER TABLE job_descriptions
    ADD COLUMN primary_resume_id INTEGER NULL,
    ADD INDEX ix_job_descriptions_primary_resume_id (primary_resume_id),
    ADD CONSTRAINT fk_job_primary_resume FOREIGN KEY (primary_resume_id)
        REFERENCES resumes(id) ON DELETE SET NULL;
