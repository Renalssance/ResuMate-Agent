from types import SimpleNamespace

from backend.agents.harness import AgentHarness
from backend.schemas.workflow import JobProfile


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
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


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
