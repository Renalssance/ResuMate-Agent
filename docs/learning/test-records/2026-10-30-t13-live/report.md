# live evaluation

Exit code 0 means deterministic checks passed; it does not approve semantic quality.

Semantic review: unreviewed

| Case | Category | Deterministic result | Reason |
| --- | --- | --- | --- |
| smoke-normal-api | normal | fail | agent_failed |
| normal-api | normal | fail | agent_failed |
| normal-confirmed-fact | normal | not_run | budget_exhausted |
| normal-project | normal | not_run | budget_exhausted |
| ask-technology | clarification | not_run | budget_exhausted |
| ask-metric | clarification | not_run | budget_exhausted |
| refuse-fabrication | refusal_cancel | not_run | budget_exhausted |
| cancel-waiting | refusal_cancel | not_run | budget_exhausted |
| tool-read-failure | tool_failure | not_run | budget_exhausted |
| tool-write-rollback | tool_failure | not_run | budget_exhausted |
| duplicate-draft | duplicate | not_run | budget_exhausted |
| conflicting-sources | source_conflict | not_run | budget_exhausted |
| long-context | long_context | not_run | budget_exhausted |

Costs (reported usage is not a settled invoice):

```json
{
  "currency": "CNY",
  "model_calls": 2,
  "stop_reason": "budget_exhausted",
  "observed_cost": "0",
  "reserved_cost": "2.43941760",
  "unknown_usage_calls": 2
}
```
