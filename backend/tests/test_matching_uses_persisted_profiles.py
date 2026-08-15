from types import SimpleNamespace

import pytest

from backend.graph.candidate_workflow import CandidateAnalysisGraph
from backend.schemas.workflow import Criterion, JobProfile, ResumeProfile


class RecordingRagStore:
    def search_resume_evidence(self, **_kwargs):
        return []


def _graph(rag_store):
    return CandidateAnalysisGraph(
        harness=SimpleNamespace(),
        rag_store=rag_store,
        repository=SimpleNamespace(),
    )


def test_matching_loads_sqlite_profiles_without_parsing_or_rag_profile_reads():
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
    rag_store = RecordingRagStore()
    job = SimpleNamespace(jd=SimpleNamespace(structured_data=job_profile.model_dump(mode="json")))
    candidate = SimpleNamespace(
        resume=SimpleNamespace(structured_data=resume_profile.model_dump(mode="json"))
    )
    state = {
        "user_id": 7,
        "run_id": 11,
        "candidate_id": 13,
        "resume_document_id": 21,
        "job": job,
        "candidate": candidate,
    }

    result = _graph(rag_store).load_structured_profiles(state)

    assert result["job_profile"] == job_profile
    assert result["resume_profile"] == resume_profile
    assert not hasattr(rag_store, "load_document_profile")


def test_matching_requires_sqlite_profiles():
    state = {
        "user_id": 7,
        "job": SimpleNamespace(jd=SimpleNamespace(structured_data=None)),
        "candidate": SimpleNamespace(resume=SimpleNamespace(structured_data=None)),
    }

    with pytest.raises(ValueError, match="SQLite is missing"):
        _graph(RecordingRagStore()).load_structured_profiles(state)
