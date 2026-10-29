# T13 C independent telemetry review

Reviewed worktree: `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`, against base `4f4f201` and the binding `/tmp/resumate-t13-brief.md`.

Scope: `backend/agent_runtime/telemetry.py`, `factory.py`, `runner.py`, `tools.py`, `backend/tests/test_agent_telemetry.py`, `pyproject.toml`, `uv.lock`, and `.env.example`. Adjacent runtime/SDK source was read only to establish the behavior of these changes. No implementation edits and no repeated test runs.

## Finding

### P2 — Preserve SDK tool error results instead of reporting them as success

Location: `backend/agent_runtime/telemetry.py:201–204` (`SDKToolTelemetry.on_tool_end`).

`on_tool_end` always finishes the span with `succeeded`, but the supported filesystem tools report ordinary failures by returning `ToolMessage(status='error')`. For example, the installed DeepAgents `read_file` implementation returns this result when a requested file does not exist (`deepagents/middleware/filesystem.py:2185–2189`). LangChain preserves a returned `ToolMessage` and delivers it to `on_tool_end`; only raised exceptions go to `on_tool_error` (`langchain_core/tools/base.py:1132–1135`, `_format_output` at 1391 onward).

Consequently, a model reading an incorrect or missing artifact path produces a successful Langfuse tool span even though the actual tool failed. This is reachable through the project's registered `read_file` tool and obscures the failures T13 is intended to expose.

Keep the fix narrow: recognize the typed `ToolMessage.status == 'error'` outcome, finish it as failed with a fixed controlled code, and leave the content unread/unexported. Cover an actual missing-file tool result, alongside an ordinary successful result. No error-message parsing or new instrumentation layer is needed.

No P1 findings.

## Verdict

Spec: one correction required for truthful built-in tool outcomes; the rest of the reviewed telemetry contract is correctly implemented.

Quality: request changes for the single P2 above. No broader refactor or defensive framework is warranted.

## Correct parts

- Run UUID trace identity, session, validated request UUID, immutable attempt/epoch snapshot, fixed input-version references, and artifact identities are carried through the observations without adding hashes.
- The callback is attached to the actual model before agent and summarization construction. The main model, SDK summarization, and SDK summary retry path therefore use the same callback. Existing budget/call-recording callbacks are preserved; telemetry does not wrap or consume their exceptions. The existing summary retry predicate excludes `RunError`, preserving fail-closed budget behavior.
- Call ordering is represented by actual SDK call UUIDs and an invocation-local call index. Avoiding a fabricated logical retry ordinal is correct given the observed loss of SDK retry tags.
- Business tool spans surround actual execution and close in `finally`. Interrupts close as paused; resumed execution creates a new span. Completion-event write failures also close the span.
- Export arguments are selected metadata only. Prompt/message content, tool arguments, response bodies, private answers, credentials, headers, provider URLs, and model-generated tool-call IDs are not passed into the SDK. Input-version memories are stored identity references, not memory text.
- Missing/partial configuration and explicit disable return before importing Langfuse. SDK construction/start/update/end failures disable optional tracing without changing the business path. No per-event/per-run synchronous flush or authentication check was added.
- The optional dependency is pinned to `langfuse==5.0.4`; `.env.example` describes its supported self-hosted minimum and opt-in setup.

## Actual v5 API review

The official v5.0.4 `LangfuseObservationWrapper.update` signature accepts `usage_details: Optional[Dict[str, int]] = None`. `LangfuseAgent` and `LangfuseTool` inherit that method, so `_Observation.finish` passing `usage_details=None` for agent/tool observations is compatible. The method applies generation attributes only to generation-like observation types. Root `trace_context`, child `start_observation`, `model`, `metadata`, `level`, and `end()` use the current API. [Official v5.0.4 span source](https://raw.githubusercontent.com/langfuse/langfuse-python/v5.0.4/langfuse/_client/span.py), [official v5.0.4 client source](https://raw.githubusercontent.com/langfuse/langfuse-python/v5.0.4/langfuse/_client/client.py).

`should_export_span=is_langfuse_span` is the documented way to replace the broader default filter with Langfuse-SDK-only export. It is appropriate for this manual-observation adapter. [Official filtering documentation](https://langfuse.com/docs/observability/sdk/advanced-features#filtering-by-instrumentation-scope).

The stated Langfuse Cloud/self-hosted >=4.59.0 requirement matches the official v5 upgrade guide. [Official compatibility guidance](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v4-to-v5).

## Evidence and limits

This was an independent source/spec review, including the actual installed SDK's tool-return path and the official pinned Langfuse source. The supplied `43 passed / 41 skipped` report was read, but those tests were not rerun or claimed as independently executed. The existing tests meaningfully cover real graph/checkpoint, summary/retry, pause/resume, failure isolation, privacy, and budget-callback composition; they currently omit the error-valued `on_tool_end` outcome above.

The parent will perform the synchronized-lock integration checks and real locked Langfuse client API probe without cloud export. No real Langfuse configuration, authentication, delivery, or server compatibility has been validated here. Fake-client records are not evidence of cloud receipt.
