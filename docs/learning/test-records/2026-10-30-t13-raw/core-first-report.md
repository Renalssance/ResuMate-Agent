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
