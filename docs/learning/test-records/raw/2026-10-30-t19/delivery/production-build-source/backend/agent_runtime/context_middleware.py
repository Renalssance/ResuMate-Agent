"""Business context around the SDK's own summarization and recovery engine."""
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from backend.agent_runtime.context import estimate_tokens, json_text, model_budget
from backend.services.agent_runs import RunError


class BusinessContextMiddleware(SummarizationMiddleware):
    # DeepAgents replaces the default by name, preserving its position before
    # prompt-caching/model dispatch. Do not stack a second summarization engine.
    @property
    def name(self):
        return 'SummarizationMiddleware'

    def __init__(self, *, model, backend, run_id, epoch):
        self.run_id, self.epoch = run_id, epoch
        self.budget = model_budget(model)
        capacity = model.profile['max_input_tokens']
        super().__init__(model=model, backend=backend, trigger=('fraction', .75),
                         keep=('fraction', .10), token_counter=estimate_tokens,
                         trim_tokens_to_summarize=int(capacity * .4))
        # Keep SDK retry policy/backoff/attempt cap. Put the fence and injection
        # inside that retry boundary so even a retried summary checks fresh SQL.
        retry = self._lc_helper._summary_model
        predicate = retry.retry_exception_types
        self._lc_helper._summary_model = retry.model_copy(update={
            'bound': RunnableLambda(self._summary_input) | model,
            'retry_exception_types': lambda exc: not isinstance(exc, RunError) and predicate(exc),
        })

    def _bundle(self):
        from backend.agent_runtime.tools import context_bundle
        return context_bundle(self.run_id, self.epoch, budget=self.budget)

    def _required_message(self, bundle, *, summary=False):
        return SystemMessage(content=(
            '必保留业务上下文（摘要调用）\n' if summary else '必保留业务上下文\n'
        ) + json_text(bundle.required))

    @staticmethod
    def _fail():
        raise RunError(422, 'context_budget_exceeded',
                       '本次必保留资料或工具开销超出上下文预算，请提高已核实容量、降低输出上限或减少本次资料。')

    def _summary_input(self, prompt):
        bundle = self._bundle()
        messages = [self._required_message(bundle, summary=True), HumanMessage(content=prompt)]
        # Same reserve as SDK _input_budget; this is a new summary request, not
        # another subtraction from the already-budgeted main request.
        capacity = self.model.profile['max_input_tokens']
        budget = int(capacity * .95) - (getattr(self.model, 'max_tokens', None) or 0)
        if estimate_tokens(messages) > budget:
            self._fail()
        return messages

    def wrap_model_call(self, request, handler):
        bundle = self._bundle()
        required = self._required_message(bundle)
        original = request.system_message
        blocks = [*(original.content_blocks if original else []),
                  {'type': 'text', 'text': required.content}]
        request = request.override(system_message=SystemMessage(content=blocks))
        budget = self._input_budget(request)
        required_tokens = self._count_tokens([], request.system_message, request.tools)
        if budget is None or required_tokens >= budget:
            self._fail()
        # SDK still chooses the history partition, trims and generates summary.
        # Its summary prompt has independent overhead in addition to required SQL.
        summary_overhead = estimate_tokens([required, HumanMessage(
            content=self._lc_helper.summary_prompt.format(messages=''))])
        self._lc_helper.trim_tokens_to_summarize = max(1, int((budget - summary_overhead) * .7))

        def guarded_handler(reduced):
            self._bundle()  # also fence SDK overflow retries and post-summary calls
            return handler(reduced)

        try:
            return super().wrap_model_call(request, guarded_handler)
        except ContextOverflowError as error:
            raise RunError(422, 'context_budget_exceeded',
                           '压缩后上下文仍超出预算，请提高已核实容量或减少本次资料。') from error
