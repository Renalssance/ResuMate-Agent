"""Interview evidence taken only from actual SDK inputs and public model outputs."""
from copy import deepcopy
import json
import re

from evals.budget import BudgetCallback
from evals.records import CallRecorder, public_message, public_text


def _unpage(value):
    if isinstance(value, dict):
        if 'textChunks' in value and value.get('join') == '':
            return ''.join(value['textChunks'])
        return {key: _unpage(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unpage(item) for item in value]
    return value


class InterviewEvidence:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interview_calls = []
        self.interview_summaries = []
        self.after_response = None
        self._interview_records = {}
        self._contexts = {}
        self._manifests = {}
        self._pages = {}
        self._tool_calls = {}
        self._seen_tools = set()
        self._context_call_ids = {}

    def _required(self, messages, call_id, kind):
        required_blocks, tool_inputs = [], []
        identity = (self.business_run_id, self.epoch)
        for batch in messages:
            for message in batch:
                if getattr(message, 'type', None) == 'system':
                    blocks = message.content if isinstance(message.content, list) else [{'text': public_text(message)}]
                    for block in blocks:
                        text = block.get('text', '') if isinstance(block, dict) else ''
                        if text.startswith(('必保留业务上下文\n', '必保留业务上下文（摘要调用）\n')):
                            required, _ = json.JSONDecoder().raw_decode(text[text.index('{'):])
                            required_blocks.append(required)
                for tool in getattr(message, 'tool_calls', []) or []:
                    if tool['name'] in {'get_interview_context', 'read_file'}:
                        self._tool_calls[(identity, tool['id'])] = deepcopy(tool)
                tool_id = getattr(message, 'tool_call_id', None)
                tool = self._tool_calls.get((identity, tool_id))
                if tool is None or getattr(message, 'status', 'success') != 'success':
                    continue
                text = public_text(message)
                tool_inputs.append({'tool_call_id': tool_id, 'name': tool['name'],
                                    'args': deepcopy(tool['args']), 'content': text})
                seen = (identity, tool_id)
                if seen in self._seen_tools:
                    continue
                self._seen_tools.add(seen)
                self._context_call_ids.setdefault(identity, []).append(call_id)
                if tool['name'] == 'get_interview_context':
                    context = json.loads(text)
                    if context.get('format') == 'artifact_manifest':
                        self._manifests[identity] = context['artifacts']
                    else:
                        self._contexts[identity] = context
                elif tool['name'] == 'read_file':
                    body = re.split(r'^@@ lines [^\n]*@@\n', text, maxsplit=1, flags=re.MULTILINE)
                    if len(body) == 2:
                        path = tool['args'].get('file_path') or tool['args'].get('path')
                        self._pages.setdefault((identity, path), {})[tool['args'].get('offset', 0)] = body[1]
                        self.file_reads.append(path)
        required = required_blocks[0] if len(required_blocks) == 1 else {}
        manifest = self._manifests.get(identity)
        if manifest and required:
            values = {}
            for descriptor in manifest:
                chunks = self._pages.get((identity, descriptor['path']), {})
                offset = 0
                parts = []
                for start, body in sorted(chunks.items()):
                    if start != offset:
                        break
                    parts.append(body)
                    offset += len(body.splitlines())
                if offset < descriptor['lines']:
                    break
                values[descriptor['kind']] = _unpage(json.loads('\n'.join(parts)))
            if len(values) == len(manifest):
                self._contexts[identity] = {'interviewId': required['interviewId'],
                    'expectedTurn': required['expectedTurn'], 'source': values['source'],
                    'turns': values['turns'], 'memories': deepcopy(required['memories'])}
        record = {'run_id': self.business_run_id, 'sdk_call_id': call_id, 'attempt': self.attempt,
                  'execution_epoch': self.epoch, 'required': deepcopy(required),
                  'tool_inputs': tool_inputs, 'required_block_count': len(required_blocks)}
        if identity in self._contexts:
            record['context'] = deepcopy(self._contexts[identity])
            record['context_input_call_ids'] = list(dict.fromkeys(self._context_call_ids[identity]))
        (self.interview_summaries if kind == 'summary' else self.interview_calls).append(record)
        self._interview_records[call_id] = record
        return deepcopy(record)

    def on_llm_end(self, response, *, run_id, **kwargs):
        # Settle the real response before a cancellation barrier blocks its delivery.
        super().on_llm_end(response, run_id=run_id, **kwargs)
        record = self._interview_records.get(str(run_id))
        if record is None:
            return
        generations = response.generations
        message = getattr(generations[0][0], 'message', None) if generations and generations[0] else None
        output = public_message(message)
        record['public_output'] = output
        steps = [call['args'] for call in output['tool_calls'] if call['name'] == 'InterviewStep']
        if len(steps) == 1:
            record['step'] = deepcopy(steps[0])
            if self.after_response is not None:
                self.after_response(record)


class InterviewCallRecorder(InterviewEvidence, CallRecorder):
    pass


class InterviewBudgetRecorder(InterviewEvidence, BudgetCallback):
    pass
