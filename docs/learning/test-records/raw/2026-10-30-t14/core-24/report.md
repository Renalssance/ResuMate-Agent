# stub evaluation

Exit code 0 means deterministic checks passed; it does not approve semantic quality.

Semantic review: not_applicable

| Case | Category | Deterministic result | Reason |
| --- | --- | --- | --- |
| normal-api | normal | pass |  |
| normal-confirmed-fact | normal | pass |  |
| normal-project | normal | pass |  |
| ask-technology | clarification | pass |  |
| ask-metric | clarification | pass |  |
| refuse-fabrication | refusal_cancel | pass |  |
| cancel-waiting | refusal_cancel | pass |  |
| tool-read-failure | tool_failure | pass | eval_context_unavailable |
| tool-write-rollback | tool_failure | pass | agent_failed |
| duplicate-draft | duplicate | pass |  |
| conflicting-sources | source_conflict | pass |  |
| long-context | long_context | pass |  |
| recovery-model-before-return | process_recovery | pass |  |
| recovery-draft-after-commit | process_recovery | pass |  |
| recovery-checkpoint-before-terminal | process_recovery | pass |  |
| recovery-answer-before-delivery | process_recovery | pass |  |
| parse-upload-stable-identity | durable_task | pass |  |
| parse-reparse-saved-job | durable_task | pass |  |
| match-partial-candidate-replay | durable_task | pass |  |
| question-result-replay | durable_task | pass |  |
| followup-result-replay | durable_task | pass |  |
| cancel-recovery | durable_task | pass |  |
| source-deleted-or-reassigned | durable_task | pass |  |
| business-write-rollback | durable_task | pass |  |
