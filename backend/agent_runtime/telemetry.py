"""Optional, metadata-only Langfuse v5 observations at real execution boundaries.

Business state and budget enforcement never depend on this adapter. In particular,
this is not Langfuse's full-content LangChain callback integration.
"""
import logging
import os
from time import monotonic
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from openai import APIConnectionError, APITimeoutError, APIStatusError

from backend.services.agent_runs import RunError

logger = logging.getLogger(__name__)
_SDK_TOOLS = frozenset({'ls', 'read_file', 'write_file', 'edit_file', 'glob', 'grep', 'write_todos'})


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _configured_client():
    keys = [os.getenv(name) for name in ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL')]
    if not all(keys) or os.getenv('LANGFUSE_TRACING_ENABLED', '').lower() == 'false':
        return None
    # No SDK import, authentication request, or exporter setup on the default path.
    from langfuse import Langfuse
    from langfuse.span_filter import is_langfuse_span
    return Langfuse(public_key=keys[0], secret_key=keys[1], base_url=keys[2],
                    should_export_span=is_langfuse_span)


def error_code(error):
    if isinstance(error, RunError):
        return error.code  # Codes are defined by our services, never provider bodies.
    if isinstance(error, APITimeoutError):
        return 'model_timeout'
    if isinstance(error, APIConnectionError):
        return 'model_connection_failed'
    if isinstance(error, APIStatusError):
        return 'model_http_error'
    return 'execution_failed'


def _versions(versions):
    result = {key: versions[key] for key in ('resume', 'jd', 'resumeVersion') if key in versions}
    if 'facts' in versions:
        result['facts'] = [{'factId': item['factId'], 'revision': item['revision']} for item in versions['facts']]
    if 'memories' in versions:
        result['memories'] = list(versions['memories'])
    return result


class RunTelemetry:
    """One attempt/epoch's observations, all sharing the business Run UUID trace."""
    def __init__(self, run):
        self.enabled = False
        self.failed = False
        self.root = None
        self.metadata = {}
        self.model_calls = 0
        try:
            client = _configured_client()
            if client is None:
                return
            self.metadata = {'run_id': run.id, 'session_id': run.session_id,
                'attempt': run.attempt, 'execution_epoch': run.execution_epoch,
                'input_versions': _versions(run.input_versions)}
            request_id = _uuid(run.request_id)
            if request_id:
                self.metadata['request_id'] = request_id
            self.enabled = True
            self.root = self._start(client, 'tailoring', 'agent', {},
                                    trace_context={'trace_id': UUID(run.id).hex})
        except Exception:
            self.disable()

    def disable(self):
        self.enabled = False
        if not self.failed:
            self.failed = True
            logger.warning('Optional telemetry unavailable; continuing business execution')

    def _start(self, parent, name, kind, metadata, **kwargs):
        if not self.enabled:
            return None
        try:
            values = {**self.metadata, **metadata}
            started = monotonic()
            span = parent.start_observation(name=name, as_type=kind, metadata=values, **kwargs)
            return _Observation(self, span, values, started)
        except Exception:
            self.disable()
            return None

    def start(self, name, kind, metadata=None, **kwargs):
        if not self.enabled or self.root is None:
            return None
        return self._start(self.root.span, name, kind, metadata or {}, **kwargs)

    def finish(self, run):
        if self.root:
            refs = [{'type': 'resume_version', 'id': ref['id']} for ref in run.output_refs
                    if ref.get('type') == 'resume_version']
            self.root.finish(run.status.value, error=run.error_code, output_refs=refs)


class _Observation:
    def __init__(self, trace, span, metadata, started):
        self.trace, self.span, self.metadata, self.started = trace, span, metadata, started

    def finish(self, status, *, error=None, usage=None, result_ref=None, output_refs=None):
        if not self.trace.enabled:
            return
        try:
            metadata = {**self.metadata, 'status': status, 'elapsed_ms': round((monotonic() - self.started) * 1000, 3)}
            if error:
                metadata['error_code'] = error
            if result_ref:
                metadata['result_ref'] = result_ref
            if output_refs is not None:
                metadata['output_refs'] = output_refs
            self.span.update(metadata=metadata, usage_details=usage,
                             level='ERROR' if error else 'DEFAULT')
            self.span.end()
        except Exception:
            self.trace.disable()


def _usage(response):
    # Final usage only; streamed increments and response text are never exported.
    totals = {}
    for batch in response.generations:
        for generation in batch:
            values = getattr(getattr(generation, 'message', None), 'usage_metadata', None)
            if values:
                for source, target in (('input_tokens', 'input'), ('output_tokens', 'output'), ('total_tokens', 'total')):
                    value = values.get(source)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        totals[target] = totals.get(target, 0) + value
    return totals or None


class ModelTelemetry(BaseCallbackHandler):
    """Attached to the model itself, including SDK summary calls and retries."""
    run_inline = True
    raise_error = False

    def __init__(self, trace, model_name):
        self.trace, self.model_name = trace, model_name
        self.calls = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        purpose = 'summary' if (metadata or {}).get('lc_source') == 'summarization' else 'main'
        # SDK summary retries can discard retry tags at sequence steps. Record
        # the actual call sequence, without inventing a logical retry parent.
        self.trace.model_calls += 1
        self.calls[run_id] = self.trace.start('model.' + purpose, 'generation',
            {'sdk_call_id': str(run_id), 'purpose': purpose, 'model_call_index': self.trace.model_calls},
            model=self.model_name)

    def on_llm_end(self, response, *, run_id, **kwargs):
        span = self.calls.pop(run_id, None)
        if span:
            span.finish('succeeded', usage=_usage(response))

    def on_llm_error(self, error, *, run_id, **kwargs):
        span = self.calls.pop(run_id, None)
        if span:
            span.finish('failed', error=error_code(error))


def attach_model_telemetry(model, trace):
    # Harnesses may reuse the same model after a checkpoint reopen. Replace only
    # our old observation callback; budget callbacks retain their fail-closed policy.
    callbacks = [callback for callback in model.callbacks or [] if not isinstance(callback, ModelTelemetry)]
    if trace is not None and trace.enabled:
        callbacks.append(ModelTelemetry(trace, model.model_name))
    model.callbacks = callbacks


class SDKToolTelemetry(BaseCallbackHandler):
    """Observe built-in filesystem/planning tools; business tools wrap their SQL boundary."""
    run_inline = True
    raise_error = False

    def __init__(self, trace):
        self.trace, self.calls = trace, {}

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = (serialized or {}).get('name')
        if name in _SDK_TOOLS:
            self.calls[run_id] = self.trace.start(name, 'tool', {'sdk_call_id': str(run_id)})

    def on_tool_end(self, output, *, run_id, **kwargs):
        span = self.calls.pop(run_id, None)
        if span:
            failed = isinstance(output, ToolMessage) and output.status == 'error'
            span.finish('failed' if failed else 'succeeded',
                        error='tool_result_error' if failed else None)

    def on_tool_error(self, error, *, run_id, **kwargs):
        span = self.calls.pop(run_id, None)
        if span:
            span.finish('paused' if isinstance(error, GraphInterrupt) else 'failed',
                        error=None if isinstance(error, GraphInterrupt) else error_code(error))
