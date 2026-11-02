from types import SimpleNamespace

from backend.agents.harness import AgentHarness
from backend.schemas.workflow import JobProfile
import pytest
from backend.services.agent_runs import RunError


VALID_JOB_PROFILE = """
{
  "job_title": "Backend Engineer",
  "summary": "Build backend services",
  "responsibilities": ["Build APIs"],
  "criteria": [
    {
      "criterion_id": "c1",
      "name": "Python",
      "description": "Python backend experience",
      "importance": "must",
      "weight": 100,
      "evidence_query": "Python backend projects"
    }
  ],
  "interview_focus": ["API design"]
}
"""


def completion_response(content, kwargs, finish_reason="stop"):
    if not kwargs.get('stream'):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)])
    from contextlib import nullcontext
    return nullcontext(iter([SimpleNamespace(usage=None, choices=[SimpleNamespace(
        index=0, delta=SimpleNamespace(content=content), finish_reason=finish_reason)])]))


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = []
        self.responses = [
            '{"job_profile": {"title": "Backend Engineer", "criteria": []}}',
            VALID_JOB_PROFILE,
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses[len(self.calls) - 1]
        return completion_response(content, kwargs)


def test_run_schema_injects_schema_and_retries_validation_failure(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeCompletions()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="document.parse_jd",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert len(completions.calls) == 2
    first_system_message = completions.calls[0]["messages"][0]["content"]
    assert '"criterion_id"' in first_system_message
    assert '"summary"' in first_system_message
    retry_message = completions.calls[1]["messages"][-1]["content"]
    assert "validation" in retry_message.lower()
    assert "job_profile" in retry_message


def test_harness_defaults_avoid_duplicate_long_llm_requests(monkeypatch):
    created_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_kwargs.update(kwargs)

    monkeypatch.setattr("backend.agents.harness.OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "compatible-model")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT_SECONDS", raising=False)

    harness = AgentHarness()

    assert harness.request_timeout == 300.0
    assert created_kwargs["max_retries"] == 0


def test_run_schema_publishes_agent_lifecycle_events(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeCompletions()
    events = []
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    harness.progress_callback = lambda **event: events.append(event)

    result = harness.run_schema(
        task="document.parse_jd",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
        task_id="task-llm",
        progress_stage="llm_analyze",
        progress=45,
    )

    assert result.job_title == "Backend Engineer"
    agents = [
        event["data"]["agent"]
        for event in events
        if "agent" in event["data"]
    ]

    assert [event["phase"] for event in agents] == [
        "prompt_uploading",
        "waiting_response",
        "receiving_response",
        "validating_response",
        "reflecting",
        "waiting_response",
        "receiving_response",
        "validating_response",
        "completed",
    ]
    assert agents[0]["task"] == "document.parse_jd"
    assert agents[0]["schema"] == "JobProfile"
    assert agents[4]["attempt"] == 1
    assert agents[4]["level"] == "warning"


class FakeReflectionCompletions:
    def __init__(self) -> None:
        self.calls = []
        self.responses = [
            '{"job_profile": {"title": "Backend Engineer", "criteria": []}}',
            '{"job_title": "Backend Engineer", "summary": "Build backend services", "criteria": []}',
            VALID_JOB_PROFILE,
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses[len(self.calls) - 1]
        return completion_response(content, kwargs)


def test_run_schema_allows_two_reflections_with_validation_feedback(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeReflectionCompletions()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="document.parse_jd",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert len(completions.calls) == 3
    first_reflection = completions.calls[1]["messages"][-1]["content"]
    second_reflection = completions.calls[2]["messages"][-1]["content"]
    assert "Reflection attempt 1 of 2" in first_reflection
    assert "Reflection attempt 2 of 2" in second_reflection
    assert "Validation errors" in first_reflection
    assert "Validation errors" in second_reflection


class FakeLengthLimitedCompletions:
    def __init__(self) -> None:
        self.calls = []
        self.truncated_content = '{"job_title": "Backend Engineer"'

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return completion_response(self.truncated_content, kwargs, "length")
        return completion_response(VALID_JOB_PROFILE, kwargs)



def test_run_schema_retries_length_truncation_with_more_tokens(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeLengthLimitedCompletions()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.max_tokens = 8192
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="document.parse_jd",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert [call["max_tokens"] for call in completions.calls] == [8192, 16384]
    assert all(
        message["content"] != completions.truncated_content
        for message in completions.calls[1]["messages"]
    )


class FakeUnsupportedResponseFormatCompletions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format", {}).get("type") == "json_schema":
            raise Exception(
                "Error code: 400 - {'error': {'message': 'This response_format type is unavailable now', "
                "'type': 'invalid_request_error', 'param': None, 'code': 'invalid_request_error'}}"
            )
        return completion_response(VALID_JOB_PROFILE, kwargs)


def test_run_schema_falls_back_when_response_format_is_unavailable(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeUnsupportedResponseFormatCompletions()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="document.parse_jd",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert len(completions.calls) == 2
    assert "response_format" in completions.calls[0]
    assert completions.calls[1]["response_format"] == {"type": "json_object"}


def test_resume_and_jd_parsing_disable_deepseek_thinking(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    for task in ("document.parse_jd", "document.parse_resume"):
        completions = FakeCompletions()
        completions.responses = [VALID_JOB_PROFILE]
        harness = AgentHarness.__new__(AgentHarness)
        harness.model = "deepseek-v4-flash"
        harness.base_url = "https://api.deepseek.com"
        harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        result = harness.run_schema(
            task=task,
            prompt_name="parse_jd",
            schema=JobProfile,
            variables={"jd_text": "Backend Engineer JD"},
        )

        assert result.job_title == "Backend Engineer"
        assert completions.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
        assert "thinking" not in completions.calls[0]


def test_other_deepseek_tasks_do_not_disable_thinking(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeCompletions()
    completions.responses = [VALID_JOB_PROFILE]
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "deepseek-v4-flash"
    harness.base_url = "https://api.deepseek.com"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="evaluate_match",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert "extra_body" not in completions.calls[0]
    assert "thinking" not in completions.calls[0]


def test_deepseek_resume_and_jd_parsing_start_with_json_object(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    for task in ("document.parse_jd", "document.parse_resume"):
        completions = FakeCompletions()
        completions.responses = [VALID_JOB_PROFILE]
        harness = AgentHarness.__new__(AgentHarness)
        harness.model = "deepseek-v4-flash"
        harness.base_url = "https://api.deepseek.com"
        harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        result = harness.run_schema(
            task=task,
            prompt_name="parse_jd",
            schema=JobProfile,
            variables={"jd_text": "Backend Engineer JD"},
        )

        assert result.job_title == "Backend Engineer"
        assert completions.calls[0]["response_format"] == {"type": "json_object"}


class FakeJsonObjectUnsupportedCompletions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format", {}).get("type") == "json_object":
            raise Exception(
                "Error code: 400 - {'error': {'message': 'This response_format type is unavailable now', "
                "'type': 'invalid_request_error', 'param': None, 'code': 'invalid_request_error'}}"
            )
        return completion_response(VALID_JOB_PROFILE, kwargs)


def test_deepseek_parsing_falls_back_without_response_format(monkeypatch):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = FakeJsonObjectUnsupportedCompletions()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "deepseek-v4-flash"
    harness.base_url = "https://api.deepseek.com"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = harness.run_schema(
        task="document.parse_resume",
        prompt_name="parse_jd",
        schema=JobProfile,
        variables={"jd_text": "Backend Engineer JD"},
    )

    assert result.job_title == "Backend Engineer"
    assert len(completions.calls) == 2
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in completions.calls[1]


@pytest.mark.parametrize("completions_factory", [FakeCompletions, FakeUnsupportedResponseFormatCompletions])
def test_cancelled_retry_or_fallback_never_starts_another_model_call(monkeypatch, completions_factory):
    monkeypatch.setattr(AgentHarness, "load_prompt", staticmethod(lambda name: "Parse {{jd_text}}"))
    completions = completions_factory()
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = "compatible-model"
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    def guard():
        if completions.calls:
            raise RunError(409, "execution_lost", "cancelled")
    harness.guard = guard
    with pytest.raises(RunError, match="cancelled"):
        harness.run_schema(task="evaluate_match", prompt_name="parse_jd", schema=JobProfile,
                           variables={"jd_text": "Backend Engineer JD"})
    assert len(completions.calls) == 1


@pytest.mark.parametrize('task', ['document.parse_resume', 'document.parse_jd', 'chat'])
def test_only_resume_extraction_explicitly_disables_reasoning_in_http_request(task):
    import json
    import httpx
    from openai import OpenAI

    def respond(request):
        body = json.loads(request.content)
        if task == 'document.parse_resume':
            assert body.get('reasoning_effort') == 'none'
        else:
            assert 'reasoning_effort' not in body
        if body.get('stream'):
            chunk = dict(id='parse', object='chat.completion.chunk', created=0, model='iq3_xxs',
                         choices=[dict(index=0, delta={'content': '{}'}, finish_reason='stop')])
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json=dict(id='chat', object='chat.completion', created=0,
            model='iq3_xxs', choices=[dict(index=0, message={'role': 'assistant', 'content': '{}'}, finish_reason='stop')]))

    harness = AgentHarness.__new__(AgentHarness)
    harness.model = 'iq3_xxs'
    with OpenAI(api_key='test', base_url='https://model.test/v1', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        harness.client = client
        result = harness._create_chat_completion(task, [{'role': 'user', 'content': 'Extract fields'}], None, 0)
    assert result.choices[0].message.content == '{}'


@pytest.mark.parametrize('length_error', [False, True])
def test_document_stream_assembles_json_and_usage_before_validation(monkeypatch, length_error):
    import json
    import httpx
    from openai import OpenAI
    requests, events, usages = [], [], []
    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body.get('stream') is True
        assert body['stream_options'] == {'include_usage': True}
        if length_error and len(requests) == 1:
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text='data: '+json.dumps({
                'error': {'message': 'structured output was incomplete (finish_reason=length); increase the output budget'}
            })+'\n\n')
        parts = [VALID_JOB_PROFILE[:100], VALID_JOB_PROFILE[100:]]
        chunks = [dict(id='parse', object='chat.completion.chunk', created=0, model='test',
            choices=[dict(index=0, delta={'content': part}, finish_reason=None)]) for part in parts]
        chunks += [dict(id='parse', object='chat.completion.chunk', created=0, model='test',
            choices=[dict(index=0, delta={}, finish_reason='stop')]),
            dict(id='parse', object='chat.completion.chunk', created=0, model='test', choices=[],
                usage={'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46})]
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
            text=''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n')
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = 'test'
    harness.progress_callback = lambda **event: events.append(event)
    monkeypatch.setattr(harness, '_record_usage_response', lambda task, response, elapsed: usages.append(response.usage))
    with OpenAI(api_key='test', base_url='https://model.test/v1', max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        harness.client = client
        result = harness.run_schema(task='document.parse_jd', prompt_name='parse_jd', schema=JobProfile, variables={'jd_text':'Build APIs'})
    assert result.job_title == 'Backend Engineer'
    assert len(requests) == (2 if length_error else 1)
    if length_error:
        assert [request['max_tokens'] for request in requests] == [8192, 16384]
    assert usages[-1].total_tokens == 46
    assert any(event['data']['agent']['phase'] == 'receiving_response' for event in events)


@pytest.mark.parametrize('cancelled', [False, True])
def test_document_stream_closes_on_cancel_or_missing_finish_marker(cancelled):
    from contextlib import contextmanager
    closed = []
    @contextmanager
    def stream(**kwargs):
        try:
            yield iter([SimpleNamespace(usage=None, choices=[SimpleNamespace(index=0,
                delta=SimpleNamespace(content=VALID_JOB_PROFILE), finish_reason=None)])])
        finally:
            closed.append(True)
    harness = AgentHarness.__new__(AgentHarness)
    harness.model = 'test'
    harness.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=stream)))
    checks = []
    def guard():
        checks.append(True)
        if cancelled and len(checks) > 1:
            raise RunError(409, 'execution_lost', 'cancelled')
    harness.guard = guard
    with pytest.raises(RunError if cancelled else RuntimeError, match='cancelled' if cancelled else '完成标记'):
        harness._create_chat_completion('document.parse_resume', [], None, 1)
    assert closed == [True]
