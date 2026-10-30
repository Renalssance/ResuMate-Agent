"""Local synthetic-evaluation records; never retain reasoning or provider errors."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from langchain_core.callbacks import BaseCallbackHandler


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def public_text(message):
    content = getattr(message, 'content', '')
    if isinstance(content, str):
        return content
    return ''.join(block.get('text', '') for block in content
                   if isinstance(block, dict) and block.get('type') == 'text')


def public_message(message):
    """Preserve proposed tool arguments even when SQL later rejects the draft."""
    return {'text': public_text(message), **{
        field: [{key: deepcopy(call.get(key)) for key in ('id', 'name', 'args')}
                for call in (getattr(message, field, None) or [])]
        for field in ('tool_calls', 'invalid_tool_calls')}}


def required_projection(required):
    """Only synthetic business preservation evidence, never prompts or answers."""
    return {**{key: deepcopy(required.get(key)) for key in ('runId', 'inputVersions', 'constraints')},
            'facts': deepcopy(required.get('facts', [])),
            'memories': deepcopy(required.get('memories', [])),
            'applicantAnswers': sorted(item['actionId'] for item in required.get('applicantAnswers', [])),
            'outputs': sorted(item['id'] for item in required.get('outputs', []))}


def response_usage(response):
    """Read final cumulative usage once, never add streaming deltas to it."""
    generations = response.generations
    message = getattr(generations[0][0], 'message', None) if generations and generations[0] else None
    usage = getattr(message, 'usage_metadata', None)
    if usage is not None and all(isinstance(usage.get(key), int) and usage[key] >= 0
                                 for key in ('input_tokens', 'output_tokens')):
        return {key: usage[key] for key in ('input_tokens', 'output_tokens')}
    usage = (response.llm_output or {}).get('token_usage')
    if isinstance(usage, dict) and all(isinstance(usage.get(key), int) and usage[key] >= 0
                                      for key in ('prompt_tokens', 'completion_tokens')):
        return {'input_tokens': usage['prompt_tokens'], 'output_tokens': usage['completion_tokens']}
    return None


class CallRecorder(BaseCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, calls_path, *, case_id, model='stub'):
        self.calls_path = Path(calls_path)
        self.case_id, self.model = case_id, model
        self.business_run_id = None
        self.attempt = 1
        self.epoch = 0
        self.calls = {}
        self.outputs = []
        self.file_reads = []
        self.required_contexts = []
        self.context_expectations = None
        self._tools = {}
        self._file_requests = {}
        self._file_responses = set()

    def _append(self, value):
        self.calls_path.parent.mkdir(parents=True, exist_ok=True)
        with self.calls_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')
            stream.flush()

    def _required(self, messages, call_id, kind):
        observed = []
        for batch in messages:
            for message in batch:
                for call in getattr(message, 'tool_calls', []) or []:
                    if call.get('name') == 'read_file':
                        args = call.get('args', {})
                        self._file_requests[call['id']] = args.get('file_path') or args.get('path')
                response_id = getattr(message, 'tool_call_id', None)
                if (getattr(message, 'name', None) == 'read_file' and response_id not in self._file_responses
                        and getattr(message, 'status', 'success') == 'success'):
                    path = self._file_requests.get(response_id)
                    if path:
                        self.file_reads.append(path)
                        self._file_responses.add(response_id)
                # Summary HumanMessages embed old transcripts. Only the current
                # injected SystemMessage is evidence for this actual request.
                if getattr(message, 'type', None) != 'system':
                    continue
                text = public_text(message)
                # Required context is a separate text block for main calls.
                blocks = message.content if isinstance(message.content, list) else [{'text': text}]
                for block in blocks:
                    raw = block.get('text', '') if isinstance(block, dict) else ''
                    injected = raw.startswith(('必保留业务上下文\n', '必保留业务上下文（摘要调用）\n'))
                    start = raw.find('{') if injected else -1
                    if start >= 0:
                        try:
                            required, _ = json.JSONDecoder().raw_decode(raw[start:])
                            observed.append(required_projection(required))
                        except (ValueError, TypeError):
                            pass
        if self.context_expectations is not None:
            expected = required_projection(self.context_expectations())
            proof = dict(sdk_call_id=call_id, attempt=self.attempt, execution_epoch=self.epoch,
                         kind=kind, expected=expected, observed=observed,
                         passed=len(observed) == 1 and observed[0] == expected)
            self.required_contexts.append(proof)
            return proof
        return None

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, reserved_cost=None, **kwargs):
        call_id = str(run_id)
        kind = 'summary' if (metadata or {}).get('lc_source') == 'summarization' else 'main'
        proof = self._required(messages, call_id, kind)
        self.start_call(call_id, kind=kind, reserved_cost=reserved_cost, proof=proof)

    def start_call(self, call_id, *, kind='main', reserved_cost=None, proof=None, **evidence):
        entry = dict(event='started', case_id=self.case_id, run_id=self.business_run_id,
                     sdk_call_id=call_id, model=self.model, attempt=self.attempt, execution_epoch=self.epoch,
                     kind=kind, started_at=utc_now(), usage=None, reserved_cost=reserved_cost,
                     observed_cost=None, **evidence)
        if proof is not None:
            entry['required_context'] = proof
        self.calls[call_id] = {**entry, '_clock': time.monotonic()}
        self._append(entry)

    def _finish(self, call_id, *, usage=None, error_code=None, output=None, error_type=None, http_status=None):
        if call_id not in self.calls:
            return
        entry = self.calls[call_id]
        if entry.get('ended_at'):
            return
        entry.update(event='failed' if error_code else 'completed', ended_at=utc_now(),
                     elapsed_ms=round((time.monotonic() - entry['_clock']) * 1000),
                     usage=usage, error_code=error_code)
        if error_code:
            entry.update(error_type=error_type, http_status=http_status)
        if entry['kind'] == 'main' and output is not None:
            entry['public_output'] = output
            self.outputs.append(output)
        self._append({key: value for key, value in entry.items() if not key.startswith('_')})

    def on_llm_end(self, response, *, run_id, **kwargs):
        generations = response.generations
        message = getattr(generations[0][0], 'message', None) if generations and generations[0] else None
        self._finish(str(run_id), usage=response_usage(response), output=public_message(message))

    def on_llm_error(self, error, *, run_id, **kwargs):
        # Deliberately omit arbitrary exception messages and provider response bodies.
        code = getattr(error, 'code', None)
        safe_codes = {'budget_exhausted', 'budget_config_mismatch', 'context_budget_exceeded'}
        status = getattr(error, 'status_code', None)
        self._finish(str(run_id), error_code=code if code in safe_codes else 'model_call_failed',
                     error_type=type(error).__name__, http_status=status if type(status) is int else None)

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
        name = (serialized or {}).get('name')
        if name == 'read_file':
            try:
                args = inputs or json.loads(input_str)
                self._tools[str(run_id)] = args.get('file_path') or args.get('path')
            except (ValueError, TypeError, AttributeError):
                pass

    def on_tool_end(self, output, *, run_id, **kwargs):
        path = self._tools.pop(str(run_id), None)
        if path:
            self.file_reads.append(path)

    def summary_calls(self):
        return sum(call['kind'] == 'summary' for call in self.calls.values())
