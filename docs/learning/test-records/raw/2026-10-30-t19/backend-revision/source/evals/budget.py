"""Sequential eval invocation budget: reserve verified worst-case cost BEFORE I/O."""
from dataclasses import MISSING, asdict, dataclass, fields
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
from pathlib import Path
from langchain_core.exceptions import ModelError
from backend.services.agent_runs import RunError
from evals.records import CallRecorder, response_usage, write_json


class BudgetExceeded(RunError, ModelError):
    is_retryable = False

    def __init__(self, code='budget_exhausted'):
        RunError.__init__(self, 422, code, 'Evaluation budget prevents another provider request')


@dataclass(frozen=True)
class BudgetConfig:
    currency: str
    max_total_cost: str
    max_case_cost: str
    input_price_per_million: str
    output_price_per_million: str
    provider_max_input_tokens: int
    context_window_tokens: int
    max_output_tokens: int
    output_token_tolerance: int
    max_model_calls: int
    max_case_model_calls: int
    request_timeout_seconds: float
    output_limit_parameter: str
    output_limit_covers_all_billed_tokens: bool
    usage: str
    model: str
    pricing_checked_at: str
    pricing_source: str
    capability_source: str
    fixed_request_cost: str = '0'
    enable_thinking: bool = False

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Live configuration must be a JSON object')
        required = {field.name for field in fields(cls) if field.default is MISSING}
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError('Missing live configuration: ' + ', '.join(missing))
        unknown = sorted(data.keys() - {field.name for field in fields(cls)})
        if unknown:
            raise ValueError('Unknown live configuration fields: ' + ', '.join(unknown))
        value = cls(**data)
        for name in ('max_total_cost', 'max_case_cost', 'input_price_per_million',
                     'output_price_per_million', 'fixed_request_cost'):
            try:
                amount = Decimal(str(getattr(value, name)))
                if not amount.is_finite() or amount < 0 or (name != 'fixed_request_cost' and amount == 0):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise ValueError('Invalid live configuration: ' + name) from None
        for name in ('provider_max_input_tokens', 'context_window_tokens', 'max_output_tokens',
                     'max_model_calls', 'max_case_model_calls'):
            number = getattr(value, name)
            if type(number) is not int or number <= 0:
                raise ValueError('Invalid live configuration: ' + name)
        if type(value.output_token_tolerance) is not int or value.output_token_tolerance < 0:
            raise ValueError('Invalid live configuration: output_token_tolerance')
        if value.output_limit_covers_all_billed_tokens is not True:
            raise ValueError('output_limit_covers_all_billed_tokens must be verified true')
        if value.output_limit_parameter != 'max_completion_tokens':
            raise ValueError('Only verified max_completion_tokens is supported')
        if value.enable_thinking is not False:
            raise ValueError('The first eval harness requires enable_thinking=false')
        if value.usage not in {'reported', 'unavailable'}:
            raise ValueError('usage must be reported or unavailable')
        if value.context_window_tokens > value.provider_max_input_tokens or int(value.context_window_tokens * .95) <= value.max_output_tokens:
            raise ValueError('Invalid context_window_tokens/output reserve')
        if not isinstance(value.request_timeout_seconds, (int, float)) or not 0 < value.request_timeout_seconds < float('inf'):
            raise ValueError('request_timeout_seconds must be finite and positive')
        if any(not isinstance(getattr(value, name), str) or not getattr(value, name).strip()
               for name in ('currency', 'model', 'pricing_checked_at', 'pricing_source', 'capability_source')):
            raise ValueError('Pricing, currency, model and capability evidence are required')
        # This known provider documents up to ten output tokens beyond the parameter.
        if value.model.startswith('qwen3.7-flash') and value.output_token_tolerance < 10:
            raise ValueError('Qwen output_token_tolerance must include the documented 10 tokens')
        return value

    def cost(self, input_tokens, output_tokens):
        return ((Decimal(input_tokens) * Decimal(str(self.input_price_per_million))
                 + Decimal(output_tokens) * Decimal(str(self.output_price_per_million))) / Decimal(1_000_000)
                + Decimal(str(self.fixed_request_cost))).quantize(Decimal('.00000001'), rounding=ROUND_CEILING)

    @property
    def reserve(self):
        return self.cost(self.provider_max_input_tokens, self.max_output_tokens + self.output_token_tolerance)

    def public(self):
        return asdict(self)


class BudgetCallback(CallRecorder):
    def __init__(self, config, ledger_path, calls_path, *, case_id):
        super().__init__(calls_path, case_id=case_id, model=config.model)
        self.config, self.ledger_path = config, Path(ledger_path)
        self.ledger = json.loads(self.ledger_path.read_text()) if self.ledger_path.exists() else {
            'currency': config.currency, 'calls': {}, 'stop_reason': None}

    def _save(self):
        write_json(self.ledger_path, self.ledger)

    def summary(self):
        entries = list(self.ledger['calls'].values())
        observed = sum((Decimal(item['observed_cost']) for item in entries if item['observed_cost'] is not None), Decimal(0))
        reserved = sum((Decimal(item['reserved_cost']) for item in entries if item['observed_cost'] is None), Decimal(0))
        return dict(currency=self.config.currency, model_calls=len(entries), observed_cost=str(observed),
                    reserved_cost=str(reserved), committed_cost=str(observed + reserved),
                    unknown_usage_calls=sum(item['observed_cost'] is None for item in entries),
                    max_total_cost=str(self.config.max_total_cost), stop_reason=self.ledger['stop_reason'],
                    condition='Verified provider prices and all billed output limit; observed usage is not a settled invoice')

    def reserve_call(self, run_id):
        """Persist one reservation before a real SDK request, including legacy calls."""
        if self.ledger['stop_reason']:
            raise BudgetExceeded(self.ledger['stop_reason'])
        entries = list(self.ledger['calls'].values())
        case_entries = [item for item in entries if item['case_id'] == self.case_id]
        case_cost = sum((Decimal(item['observed_cost'] if item['observed_cost'] is not None else item['reserved_cost'])
                         for item in case_entries), Decimal(0))
        if (len(entries) >= self.config.max_model_calls or len(case_entries) >= self.config.max_case_model_calls
                or Decimal(self.summary()['committed_cost']) + self.config.reserve > Decimal(str(self.config.max_total_cost))
                or case_cost + self.config.reserve > Decimal(str(self.config.max_case_cost))):
            self.ledger['stop_reason'] = 'budget_exhausted'
            self._save()
            raise BudgetExceeded()
        self.ledger['calls'][str(run_id)] = dict(case_id=self.case_id, reserved_cost=str(self.config.reserve),
                                                observed_cost=None, usage=None)
        self._save()  # Durable reserve precedes the actual provider request.
        return str(self.config.reserve)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        reserve = self.reserve_call(run_id)
        super().on_chat_model_start(serialized, messages, run_id=run_id, reserved_cost=reserve, **kwargs)

    def settle_call(self, run_id, usage):
        entry = self.ledger['calls'].get(str(run_id))
        if entry is not None and usage is not None:
            entry['usage'] = usage
            entry['observed_cost'] = str(self.config.cost(usage['input_tokens'], usage['output_tokens']))
            self.calls[str(run_id)]['observed_cost'] = entry['observed_cost']
            if (usage['input_tokens'] > self.config.provider_max_input_tokens
                    or usage['output_tokens'] > self.config.max_output_tokens + self.config.output_token_tolerance):
                self.ledger['stop_reason'] = 'budget_config_mismatch'
            self._save()

    def on_llm_end(self, response, *, run_id, **kwargs):
        self.settle_call(run_id, response_usage(response))
        super().on_llm_end(response, run_id=run_id, **kwargs)
