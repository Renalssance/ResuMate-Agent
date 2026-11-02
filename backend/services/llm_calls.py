"""Local, authenticated model-call inspection, separate from operational logs."""
import logging
from time import monotonic
from fastapi import HTTPException
from backend.db.database import SessionLocal
from backend.db.models import LlmCall

logger = logging.getLogger(__name__)
REQUEST_FIELDS = {'model', 'messages', 'temperature', 'max_tokens', 'max_completion_tokens',
    'timeout', 'response_format', 'reasoning_effort', 'reasoning_budget_tokens', 'thinking_budget_tokens',
    'thinking', 'chat_template_kwargs', 'stream', 'stream_options', 'tools', 'tool_choice',
    'parallel_tool_calls', 'top_p', 'stop', 'seed', 'frequency_penalty', 'presence_penalty'}


def _summary(row):
    return dict(id=row.id, task=row.task, model=row.model, base_url=row.base_url,
        attempt=row.attempt, status=row.status, usage=row.usage_json, elapsed_ms=row.elapsed_ms,
        called_at=row.called_at.isoformat() + 'Z')


def list_calls(db, user_id, offset, limit):
    query = db.query(LlmCall).filter(LlmCall.user_id == user_id)
    return {'total': query.count(), 'items': [_summary(row) for row in
        query.order_by(LlmCall.id.desc()).offset(offset).limit(limit).all()]}


def get_call(db, user_id, call_id):
    row = db.query(LlmCall).filter(LlmCall.id == call_id, LlmCall.user_id == user_id).first()
    if row is None:
        raise HTTPException(404, '调用记录不存在')
    return {**_summary(row), 'request': row.request_json, 'output': row.output_json, 'error': row.error}


class CallTrace:
    def __init__(self, user_id, task, base_url, request, attempt=1):
        self.id = None
        self.started = self.updated = monotonic()
        self.output = {'choices': []}
        self.usage = None
        self.error = ''
        self.status = 'running'
        if not user_id:
            return
        # Only request-body model settings: never SDK credentials or headers.
        request = {**request, **request.get('extra_body', {})}
        request = {k: v for k, v in request.items() if k in REQUEST_FIELDS}
        try:
            with SessionLocal() as db:
                row = LlmCall(user_id=user_id, task=task, model=request.get('model', ''),
                    base_url=base_url, attempt=attempt, request_json=request)
                db.add(row)
                db.commit()
                self.id = row.id
        except Exception:
            logger.warning('Model call inspection could not create record')

    def add_chunk(self, chunk):
        if not self.id:
            return
        if not isinstance(chunk, dict):
            chunk = chunk.model_dump(mode='json')
        if chunk.get('usage') is not None:
            self.usage = chunk['usage']
        for choice in chunk.get('choices', []):
            index = choice.get('index', 0)
            target = next((c for c in self.output['choices'] if c['index'] == index), None)
            if target is None:
                target = {'index': index, 'message': {'content': '', 'reasoning_content': ''}, 'finish_reason': None}
                self.output['choices'].append(target)
            delta = choice.get('delta', {})
            for key in ('content', 'reasoning_content'):
                target['message'][key] += delta.get(key) or ''
            if delta.get('tool_calls'):
                target['message'].setdefault('tool_call_deltas', []).extend(delta['tool_calls'])
            if choice.get('finish_reason'):
                target['finish_reason'] = choice['finish_reason']
        if monotonic() - self.updated >= 1:
            self._save()

    def finish(self, response=None, error=None):
        if not self.id:
            return
        if response is not None:
            self.output = response if isinstance(response, dict) else response.model_dump(mode='json')
            self.usage = self.output.get('usage')
        self.status = 'failed' if error else 'completed'
        if not error and any(c.get('finish_reason') == 'length' for c in self.output.get('choices', [])):
            self.status = 'truncated'
        # Error bodies may contain credentials; retain type and HTTP status only.
        self.error = f'{type(error).__name__} (HTTP {getattr(error, "status_code", "—")})' if error else ''
        self._save()

    def _save(self):
        if not self.id:
            return
        try:
            with SessionLocal() as db:
                row = db.get(LlmCall, self.id)
                row.output_json = self.output
                row.usage_json = self.usage
                row.status = self.status
                row.error = self.error
                row.elapsed_ms = round((monotonic() - self.started) * 1000)
                db.commit()
            self.updated = monotonic()
        except Exception:
            logger.warning('Model call inspection could not update record')
