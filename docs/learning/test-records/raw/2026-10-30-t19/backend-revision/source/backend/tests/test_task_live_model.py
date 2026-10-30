"""A real OpenAI client and Harness must reserve each HTTP attempt, without networking."""
import json
from decimal import Decimal

import httpx
from pydantic import BaseModel
import pytest

from backend.tests.test_eval_budget import config
from evals.budget import BudgetCallback, BudgetExceeded


class Result(BaseModel):
    value: int


def completion(value, *, usage=True):
    body = {'id': 'synthetic-completion', 'object': 'chat.completion', 'created': 1,
            'model': 'qwen3.7-flash-2026-07-15',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(value)}, 'finish_reason': 'stop'}]}
    if usage:
        body['usage'] = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}
    return httpx.Response(200, json=body)


def setup_model(tmp_path, monkeypatch, transport, **budget_updates):
    from evals.task_live_model import LiveTaskModel
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-not-secret')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://synthetic.invalid/v1')
    cfg = config(**budget_updates)
    budget = BudgetCallback(cfg, tmp_path / 'budget.json', tmp_path / 'calls.jsonl', case_id='http-contract')
    model = LiveTaskModel(cfg, budget, transport=httpx.MockTransport(transport))
    return model, budget


def execute(model, guard=None):
    harness = model.harness(user_id=None, guard=guard)
    return harness.run_schema(task='followup.analyze_answer', prompt_name='generate_followup',
                              schema=Result, variables={'question': 'How?', 'answer': 'Synthetic answer'})


def test_real_harness_fallback_and_reflection_reserve_every_http_create(tmp_path, monkeypatch):
    requests = []
    def transport(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(400, json={'error': {'message': 'response_format unsupported', 'type': 'invalid_request_error'}})
        return completion({'value': 'not-an-int'} if len(requests) == 2 else {'value': 7})
    model, budget = setup_model(tmp_path, monkeypatch, transport)
    try:
        assert execute(model).value == 7
        assert len(requests) == budget.summary()['model_calls'] == 3
        assert budget.summary()['unknown_usage_calls'] == 1
        assert Decimal(budget.summary()['observed_cost']) == Decimal('0.000432')
        assert requests[0]['response_format']['type'] == 'json_schema'
        assert requests[1]['response_format']['type'] == 'json_object'
        assert all(item['max_completion_tokens'] == 4096 and item['enable_thinking'] is False for item in requests)
        assert all('max_tokens' not in item for item in requests)
        assert [call['request'] for call in model.calls] == requests
        records = (tmp_path / 'calls.jsonl').read_text()
        assert 'synthetic-not-secret' not in records
        assert 'not-an-int' in records
    finally:
        model.close()


def test_403_without_usage_keeps_reserve_and_stops_before_unaffordable_retry(tmp_path, monkeypatch):
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(403, json={'error': {'message': 'private provider body', 'code': 'insufficient_quota'}})
    model, budget = setup_model(tmp_path, monkeypatch, transport, max_total_cost='1.3')
    try:
        with pytest.raises(BudgetExceeded):
            execute(model)
        assert len(requests) == 1
        assert budget.summary()['unknown_usage_calls'] == 1
        assert budget.summary()['reserved_cost'] == '1.21970880'
        records = (tmp_path / 'calls.jsonl').read_text()
        assert 'private provider body' not in records
        assert 'PermissionDeniedError' in records and '403' in records
    finally:
        model.close()


def test_guard_prevents_send_and_reservation(tmp_path, monkeypatch):
    from backend.services.agent_runs import RunError
    sent = []
    model, budget = setup_model(tmp_path, monkeypatch, lambda request: sent.append(request) or completion({'value': 7}))
    def cancelled():
        raise RunError(409, 'run_cancelled', 'Cancelled')
    try:
        with pytest.raises(RunError, match='Cancelled'):
            execute(model, cancelled)
        assert not sent and budget.summary()['model_calls'] == 0
    finally:
        model.close()


def test_budget_settles_received_output_before_late_cancel_hook(tmp_path, monkeypatch):
    model, budget = setup_model(tmp_path, monkeypatch, lambda request: completion({'value': 7}))
    observed = []
    model.hooks['followup.analyze_answer'] = lambda: observed.append(budget.summary())
    try:
        assert execute(model).value == 7
        assert observed[0]['unknown_usage_calls'] == 0
        assert observed[0]['model_calls'] == 1
        assert model.calls[0]['public_output']['text'] == '{"value": 7}'
    finally:
        model.close()
