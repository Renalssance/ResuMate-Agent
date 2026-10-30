"""Browser-test worker: deterministic model; real graph, tools and persistence."""
import time
import sys

from backend.tests import e2e_legacy_fixture  # noqa: F401
from backend.services import document_process

# The isolated parser must install the same synthetic providers as this worker.
document_process._command = lambda run_id, epoch: [
    sys.executable, "-m", "backend.tests.e2e_document_process", run_id, str(epoch),
]

from backend.agent_runtime import factory
from backend.tests.agent_fixtures import DraftModel
from backend.tests.interview_model_fixture import ScriptedInterviewModel
from pydantic import PrivateAttr
from backend.worker import app


class BrowserDraftModel(DraftModel):
    ask: bool = True
    _interview_model: ScriptedInterviewModel | None = PrivateAttr(default=None)

    def bind_tools(self, tools, **kwargs):
        names = {getattr(tool, 'name', None) or tool['function']['name'] for tool in tools}
        if 'get_interview_context' in names or 'InterviewStep' in names:
            if self._interview_model is None:
                state = Path(os.environ['RESUMATE_E2E_ROOT'])
                self._interview_model = ScriptedInterviewModel(
                    profile=self.profile, max_tokens=self.max_tokens,
                    long_question=(state / 'interview-long').exists(),
                    before_generate=browser_interview_before,
                    transform_step=browser_interview_step,
                )
            return self._interview_model.bind_tools(tools, **kwargs)
        return super().bind_tools(tools, **kwargs)

    def _generate(self, messages, **kwargs):
        if self._interview_model is not None:
            return self._interview_model._generate(messages, **kwargs)
        time.sleep(0.7)  # Observable real cancellation window.
        return super()._generate(messages, **kwargs)

    def draft_changes(self, context):
        changes = super().draft_changes(context)
        # Long but source-bound wording exercises wrapping without inventing metrics.
        changes[0]['after'] = changes[0]['before'] + '。' + '负责 API 和数据库设计，与团队核对接口需求。' * 8
        changes[0]['reason'] = '使用原简历与本次补充的接口职责，突出和岗位相关的实际工作。' * 3
        if context.get('facts'):
            fact = context['facts'][0]
            changes[0]['fact_refs'].append({'kind': 'profile_fact', 'factId': fact['id'], 'revision': fact['revision']})
        work = context['resume']['structured'].get('work_experience', [])
        if work:
            changes.append({'section': '/work_experience/0/description', 'before': work[0]['description'],
                            'after': None, 'reason': '职责已知，但没有可核对的规模或效果指标；请补充后再修改。',
                            'fact_refs': [], 'requires_input': True})
        return changes


_configured_model = factory.model_for_user


def browser_model_for_user(user_id):
    # Constructing the real configured client validates settings without a request.
    configured = _configured_model(user_id)
    return BrowserDraftModel(profile=configured.profile, max_tokens=configured.max_tokens)


factory.model_for_user = browser_model_for_user


# PDF browser acceptance uses the real renderer; only the test process can
# pause it or fail once to expose actionable running/error UI states.
import os
from pathlib import Path
from backend.services import resume_export

_real_render_pdf = resume_export.render_pdf


def browser_render_pdf(content, output_path):
    state = Path(os.environ['AGENT_STATE_DIR']).parent
    failure = state / 'pdf-fail-once'
    if failure.exists():
        failure.unlink()
        raise RuntimeError('Synthetic one-time PDF rendering failure')
    pause = state / 'pdf-pause'
    deadline = time.monotonic() + 20
    while pause.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    return _real_render_pdf(content, output_path)


resume_export.render_pdf = browser_render_pdf


def browser_interview_before(required):
    state = Path(os.environ['RESUMATE_E2E_ROOT'])
    deadline = time.monotonic() + 20
    while (state / 'interview-pause').exists() and time.monotonic() < deadline:
        time.sleep(0.1)


def browser_interview_step(step, context):
    failure = Path(os.environ['RESUMATE_E2E_ROOT']) / 'interview-fail-once'
    if failure.exists():
        failure.unlink()
        # A valid SDK schema with unsupported evidence must fail in the actual
        # business validator, rather than disappear into a model retry.
        step['question']['refs'][0]['quote'] = '此句不存在于任何冻结资料或已接受回答'
    return step
