-- T14: apply once after 001, 002 and 003. Existing successful responses stay unknown.
ALTER TABLE agent_runs ADD COLUMN result_json JSON NULL;
