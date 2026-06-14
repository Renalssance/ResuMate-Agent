from types import SimpleNamespace

import pytest

from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.schemas.workflow import Criterion, JobProfile, ResumeProfile


class RecordingRagStore:
    def __init__(self, profiles):
        self.profiles = profiles
        self.load_calls = []

    def load_document_profile(self, *, user_id, document_type, document_id):
        self.load_calls.append((user_id, document_type, document_id))
        return self.profiles.get((document_type, document_id))


def _graph(rag_store):
    return CandidateAnalysisGraph(
        harness=SimpleNamespace(),
        rag_store=rag_store,
        repository=SimpleNamespace(),
    )


def test_matching_loads_persisted_profiles_without_parsing():
    job_profile = JobProfile(
        job_title="Backend Engineer",
        summary="Build APIs",
        criteria=[
            Criterion(
                criterion_id="api",
                name="API",
                description="Build APIs",
                importance="must",
                weight=100,
                evidence_query="API",
            )
        ],
    )
    resume_profile = ResumeProfile(candidate_name="Persisted Candidate")
    rag_store = RecordingRagStore(
        {
            ("jd", 4): job_profile.model_dump(mode="json"),
            ("resume", 9): resume_profile.model_dump(mode="json"),
        }
    )

    state = _graph(rag_store).load_structured_profiles(
        {"user_id": 7, "jd_document_id": 4, "resume_document_id": 9}
    )

    assert state["job_profile"] == job_profile
    assert state["resume_profile"] == resume_profile
    assert rag_store.load_calls == [(7, "jd", 4), (7, "resume", 9)]


def test_matching_requires_persisted_profiles():
    with pytest.raises(ValueError, match="重新解析"):
        _graph(RecordingRagStore({})).load_structured_profiles(
            {"user_id": 7, "jd_document_id": 4, "resume_document_id": 9}
        )
