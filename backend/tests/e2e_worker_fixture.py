"""Browser-test worker: deterministic model; real graph, tools and persistence."""
import time

from backend.agent_runtime import factory
from backend.tests.agent_fixtures import DraftModel
from backend.worker import app


class BrowserDraftModel(DraftModel):
    ask: bool = True

    def _generate(self, messages, **kwargs):
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
