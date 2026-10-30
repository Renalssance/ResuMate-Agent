# T16 cross-layer backend review

Reviewed final A-owned HTTP create/snapshot/commands/events/memory routes, services/interviews.py, services/interview_commands.py, memory.py and new agent_runs integration, against the frozen T16 plan and B's actual runtime boundaries. Read relevant SQL/HTTP/locking regressions; did not rerun A's suite or root's full suite.

Correct behavior: accepted command replay precedes current-turn/status rejection; immutable ack and accepted answer persist; one transaction owns command/Run/events; parent write gate and current locking reads serialize supported concurrent commands; memory capture/guard uses agreed lock order; limiter waits do not keep SQL sessions open; cancellation preserves in-flight status until worker fence/finish; finished sessions reject late output; memory confirmation is explicit/idempotent/source-bound and deletion does not revive feedback memory.

Reported and resolved: public agent_runs.run_snapshot previously returned sessionInvalidated=false for a revoked interview_generation Run. A now includes both graph kinds and added regression. Also inspected A's final same-second ordering correction: latest generation is selected by accepted generating command ID, not random Run UUID ties. No remaining P1/P2 identified.

Runtime correctness/evidence is detailed in `/tmp/task-16-runtime-report.md`. Root owns final full-backend/browser/eval evidence. T21 has been cancelled; review did not request or introduce WebSocket work.
