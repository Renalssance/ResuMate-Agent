"""Budget must stop the actual model before spending, including SDK retries."""
from decimal import Decimal
from uuid import uuid4
import json
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult


def config(**updates):
    from evals.budget import BudgetConfig
    value = dict(currency='CNY', max_total_cost='3', max_case_cost='3',
                 input_price_per_million='1.2', output_price_per_million='4.8',
                 provider_max_input_tokens=1_000_000, context_window_tokens=64_000,
                 max_output_tokens=4096, output_token_tolerance=10,
                 max_model_calls=30, max_case_model_calls=20, request_timeout_seconds=30,
                 output_limit_parameter='max_completion_tokens',
                 output_limit_covers_all_billed_tokens=True, usage='reported',
                 model='qwen3.7-flash-2026-07-15', pricing_checked_at='2026-10-30',
                 pricing_source='https://help.aliyun.com/zh/model-studio/model-pricing',
                 capability_source='https://help.aliyun.com/zh/model-studio/qwen3-7-flash')
    value.update(updates)
    return BudgetConfig.from_dict(value)


class CountModel(BaseChatModel):
    calls: int = 0
    usage: bool = True
    fail: bool = False

    @property
    def _llm_type(self):
        return 'budget-test'

    def _generate(self, messages, **kwargs):
        self.calls += 1
        if self.fail:
            raise TimeoutError('private provider error body')
        usage = {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120} if self.usage else None
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='public', usage_metadata=usage))])


def callback(tmp_path, **updates):
    from evals.budget import BudgetCallback
    return BudgetCallback(config(**updates), tmp_path / 'budget.json', tmp_path / 'calls.jsonl', case_id='one')


def test_insufficient_reserve_prevents_actual_model_call(tmp_path):
    from evals.budget import BudgetExceeded
    budget = callback(tmp_path, max_total_cost='1')
    model = CountModel(callbacks=[budget])
    with pytest.raises(BudgetExceeded):
        model.invoke('synthetic')
    assert model.calls == 0
    assert budget.summary()['model_calls'] == 0


def test_usage_reconciles_once_and_missing_usage_keeps_full_reserve(tmp_path):
    budget = callback(tmp_path)
    model = CountModel(callbacks=[budget])
    model.invoke('synthetic')
    assert Decimal(budget.summary()['observed_cost']) == Decimal('0.000216')
    model.usage = False
    model.invoke('synthetic')
    assert Decimal(budget.summary()['reserved_cost']) == Decimal('1.2197088')
    from evals.budget import BudgetCallback
    reopened = BudgetCallback(config(), tmp_path / 'budget.json', tmp_path / 'calls.jsonl', case_id='two')
    assert reopened.summary()['model_calls'] == 2
    assert reopened.summary()['unknown_usage_calls'] == 1


def test_timeout_reserve_and_summary_retry_share_actual_call_boundary(tmp_path):
    from evals.budget import BudgetExceeded
    from langchain_core.exceptions import ModelError
    budget = callback(tmp_path, max_total_cost='1.3')
    model = CountModel(callbacks=[budget], fail=True)
    retry = model.with_retry(retry_if_exception_type=lambda error: not isinstance(error, ModelError) or error.is_retryable,
                             wait_exponential_jitter=False, stop_after_attempt=3)
    with pytest.raises(BudgetExceeded):
        retry.invoke('summary', {'metadata': {'lc_source': 'summarization'}})
    assert model.calls == 1
    assert budget.summary()['unknown_usage_calls'] == 1
    records = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert records[0]['kind'] == 'summary'
    assert 'private provider error body' not in (tmp_path / 'calls.jsonl').read_text()


def test_usage_outside_verified_capacity_stops_next_call(tmp_path):
    from evals.budget import BudgetExceeded
    budget = callback(tmp_path)
    call_id = uuid4()
    budget.on_chat_model_start({}, [[]], run_id=call_id)
    response = LLMResult(generations=[[ChatGeneration(message=AIMessage(content='public',
        usage_metadata={'input_tokens': 1_000_001, 'output_tokens': 1, 'total_tokens': 1_000_002}))]])
    budget.on_llm_end(response, run_id=call_id)
    with pytest.raises(BudgetExceeded):
        CountModel(callbacks=[budget]).invoke('synthetic')
    assert budget.summary()['stop_reason'] == 'budget_config_mismatch'


def test_unknown_billing_capability_rejected_without_calling_model():
    with pytest.raises(ValueError, match='all_billed'):
        config(output_limit_covers_all_billed_tokens=False)


@pytest.mark.parametrize('allowed_calls,expected_summary_calls', [(2, 0), (3, 1)])
def test_actual_sdk_summary_is_reserved_and_budget_rejection_not_retried(tmp_path, allowed_calls, expected_summary_calls):
    import os
    from pathlib import Path
    import subprocess
    import sys
    from evals.run import isolated_environment
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config(max_total_cost='10', max_case_cost='10', max_model_calls=allowed_calls).public()))
    script = '''
import json, os
from pathlib import Path
from evals.budget import BudgetCallback, BudgetConfig
from evals.fixtures import load_cases, seed_case, make_model
from backend.agent_runtime import factory, runner
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun
from backend.schemas.agent_runs import RunCreate
from backend.services import agent_runs
case = next(case for case in load_cases() if case['id'] == 'long-context')
seed = seed_case(case)
root = Path(os.environ['AGENT_STATE_DIR']).parent
class ObservedBudget(BudgetCallback):
    summary_starts = 0
    def on_chat_model_start(self, *args, metadata=None, **kwargs):
        if (metadata or {}).get('lc_source') == 'summarization':
            self.summary_starts += 1
        return super().on_chat_model_start(*args, metadata=metadata, **kwargs)
budget = ObservedBudget(BudgetConfig.from_dict(json.loads((root / 'config.json').read_text())),
                        root / 'budget.json', root / 'calls.jsonl', case_id=case['id'])
model = make_model(case, seed)
model.callbacks = [budget]
factory.model_for_user = lambda user_id: model
with SessionLocal() as db:
    run = agent_runs.create_run(db, seed['user_id'], RunCreate(kind='tailoring', jd_id=seed['jd_id'], resume_id=seed['resume_id'], request_id='summary-budget'))
    run_id = run.id
    epoch = agent_runs.claim_run(db, run_id)
runner.run_agent(run_id, epoch)
with SessionLocal() as db:
    run = db.get(AgentRun, run_id)
    print(json.dumps(dict(status=run.status, code=run.error_code, main_calls=model.main_calls,
         summary_calls=model.summary_calls, summary_starts=budget.summary_starts, budget=budget.summary())))
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2],
                            env=isolated_environment(tmp_path), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout.strip().splitlines()[-1])
    assert actual['code'] == 'budget_exhausted'
    assert actual['summary_calls'] == expected_summary_calls
    assert actual['summary_starts'] == 1
    assert actual['main_calls'] == 2
    assert actual['budget']['model_calls'] == allowed_calls
    assert actual['budget']['unknown_usage_calls'] == allowed_calls
    records = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert all(row['reserved_cost'] == '1.21970880' for row in records)
