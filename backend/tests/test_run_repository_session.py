from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import JobDescription, MatchResult, Resume, User
from backend.repositories.runs import SqlAlchemyRunRepository
from backend.schemas.workflow import CandidateReport, Criterion, JobProfile, ResumeProfile


def test_saved_match_is_in_immediate_summary_without_expiring_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(username="candidate-summary", password_hash="unused")
        db.add(user)
        db.flush()
        jd = JobDescription(user_id=user.id, title="Backend", raw_text="Python")
        resume = Resume(user_id=user.id, filename="resume.txt", raw_text="Python", structured_data={"candidate_name": "Candidate"})
        db.add_all([jd, resume])
        db.commit()
        repository = SqlAlchemyRunRepository(db)
        job = repository.create_run(user_id=user.id, jd=jd, resumes=[resume])
        candidate = job.candidates[0]
        assert candidate.match_result is None
        report = CandidateReport(
            run_id=job.id, candidate_id=candidate.id, candidate_name="Candidate", filename=resume.filename,
            job_profile=JobProfile(job_title="Backend", summary="Python", criteria=[Criterion(criterion_id="python", name="Python", description="Python", importance="must", weight=100, evidence_query="Python")]),
            resume_profile=ResumeProfile(candidate_name="Candidate"), evaluations=[], total_score=80,
            recommendation="strong_recommend", summary="Match",
        )

        repository.save_report(job=job, candidate=candidate, report=report)

        summary = repository.get_run(user_id=user.id, run_id=job.id)
        assert [item.candidate_id for item in summary.candidates] == [candidate.id]
        repository.save_report(job=job, candidate=candidate, report=report.model_copy(update={"total_score": 85}))
        assert db.query(MatchResult).count() == 1
        assert repository.get_run(user_id=user.id, run_id=job.id).candidates[0].total_score == 85
    engine.dispose()
