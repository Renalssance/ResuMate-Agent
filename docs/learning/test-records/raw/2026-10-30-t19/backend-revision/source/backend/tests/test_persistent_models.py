from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.database import Base
from backend.db.models import (
    AnalysisCandidate,
    AnalysisJob,
    FollowUpQuestionSet,
    InterviewQuestionSet,
    JobDescription,
    MatchResult,
    Resume,
    User,
)
from backend.repositories.runs import SqlAlchemyRunRepository


def test_document_metadata_and_workflow_report_commit_and_read(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'persistent-models.db'}")
    Base.metadata.create_all(bind=engine)

    workflow_report = {
        "run_id": "run-real-001",
        "candidate_id": "candidate-real-001",
        "candidate_name": "Real Candidate",
        "filename": "candidate.pdf",
        "job_profile": {
            "job_title": "Backend Engineer",
            "criteria": [
                {
                    "criterion_id": "python",
                    "name": "Python",
                    "weight": 100,
                    "evidence_query": "Python API experience",
                }
            ],
        },
        "evaluations": [
            {
                "criterion_id": "python",
                "score": 4,
                "evidence": [
                    {
                        "chunk_id": "resume-1-page-1",
                        "filename": "candidate.pdf",
                        "page_number": 1,
                        "section": "Experience",
                        "text": "Built production FastAPI services.",
                        "score": 0.93,
                    }
                ],
            }
        ],
        "formal_questions": [{"question": "Describe the API design."}],
    }

    with Session(engine) as session:
        user = User(username="persistent-user", password_hash="hash")
        session.add(user)
        session.flush()

        resume = Resume(
            user_id=user.id,
            filename="candidate.pdf",
            file_path="data/documents/candidate.pdf",
            document_size=123,
            parse_status="success",
            raw_text="Real uploaded resume text",
            structured_data={"candidate_name": "Real Candidate"},
        )
        jd = JobDescription(
            user_id=user.id,
            title="Backend Engineer",
            company="Example",
            filename="backend-engineer.pdf",
            file_path="data/documents/backend-engineer.pdf",
            document_size=456,
            parse_status="success",
            raw_text="Real uploaded JD text",
            structured_data={"job_title": "Backend Engineer"},
        )
        session.add_all([resume, jd])
        session.flush()

        job = AnalysisJob(user_id=user.id, jd_id=jd.id, title=jd.title, status="completed")
        session.add(job)
        session.flush()
        candidate = AnalysisCandidate(job_id=job.id, resume_id=resume.id, status="completed")
        session.add(candidate)
        session.flush()
        result = MatchResult(
            job_id=job.id,
            candidate_id=candidate.id,
            resume_id=resume.id,
            jd_id=jd.id,
            overall_score=82,
            recommendation="strong_recommend",
            report_json=workflow_report,
        )
        session.add(result)
        session.commit()
        resume_id = resume.id
        jd_id = jd.id
        result_id = result.id

    with Session(engine) as session:
        stored_resume = session.get(Resume, resume_id)
        stored_jd = session.get(JobDescription, jd_id)
        stored_result = session.get(MatchResult, result_id)

        assert stored_resume.document_size == 123
        assert stored_resume.parse_status == "success"
        assert stored_jd.filename == "backend-engineer.pdf"
        assert stored_jd.file_path == "data/documents/backend-engineer.pdf"
        assert stored_jd.document_size == 456
        assert stored_jd.parse_status == "success"
        assert stored_result.report_json == workflow_report


def test_candidate_report_hydrates_questions_from_persisted_question_sets(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'question-history.db'}")
    Base.metadata.create_all(bind=engine)

    formal_question = {
        "question": "Describe the API design.",
        "question_type": "resume_experience",
        "difficulty": "medium",
        "assessment_points": ["API design depth"],
        "related_criteria": ["python"],
        "evidence_chunk_ids": ["chunk-1"],
        "reference_answer_direction": "Explain the design tradeoffs.",
        "scoring_rubric": ["Names tradeoffs"],
        "suggested_followups": ["What would you change?"],
    }
    followup_question = {
        **formal_question,
        "question": "Clarify the ambiguous API ownership.",
        "question_type": "gap_validation",
    }
    base_report = {
        "run_id": 1,
        "candidate_id": 1,
        "candidate_name": "Real Candidate",
        "filename": "candidate.pdf",
        "job_profile": {
            "job_title": "Backend Engineer",
            "summary": "Build APIs",
            "criteria": [
                {
                    "criterion_id": "python",
                    "name": "Python",
                    "description": "Build APIs",
                    "importance": "must",
                    "weight": 100,
                    "evidence_query": "Python API experience",
                }
            ],
        },
        "resume_profile": {"candidate_name": "Real Candidate"},
        "evaluations": [],
        "total_score": 82,
        "recommendation": "strong_recommend",
        "top_strengths": ["API design"],
        "summary": "Candidate matched Backend Engineer.",
        "formal_questions": [],
        "ambiguity_followups": [],
    }

    with Session(engine) as session:
        user = User(username="question-history-user", password_hash="hash")
        session.add(user)
        session.flush()
        resume = Resume(
            user_id=user.id,
            filename="candidate.pdf",
            raw_text="Resume text",
            structured_data={"candidate_name": "Real Candidate"},
        )
        jd = JobDescription(
            user_id=user.id,
            title="Backend Engineer",
            raw_text="JD text",
            structured_data={"job_title": "Backend Engineer"},
        )
        session.add_all([resume, jd])
        session.flush()
        job = AnalysisJob(user_id=user.id, jd_id=jd.id, title=jd.title, status="completed")
        session.add(job)
        session.flush()
        candidate = AnalysisCandidate(job_id=job.id, resume_id=resume.id, status="completed")
        session.add(candidate)
        session.flush()
        result = MatchResult(
            job_id=job.id,
            candidate_id=candidate.id,
            resume_id=resume.id,
            jd_id=jd.id,
            overall_score=82,
            recommendation="strong_recommend",
            report_json=base_report,
        )
        session.add(result)
        session.add(
            InterviewQuestionSet(
                job_id=job.id,
                candidate_id=candidate.id,
                resume_id=resume.id,
                jd_id=jd.id,
                questions=[formal_question],
            )
        )
        session.add(
            FollowUpQuestionSet(
                job_id=job.id,
                candidate_id=candidate.id,
                resume_id=resume.id,
                jd_id=jd.id,
                questions=[followup_question],
            )
        )
        session.commit()
        user_id = user.id
        run_id = job.id
        candidate_id = candidate.id

    with Session(engine) as session:
        report = SqlAlchemyRunRepository(session).get_candidate_report(
            user_id=user_id,
            run_id=run_id,
            candidate_id=candidate_id,
        )

    assert report is not None
    assert [item.question for item in report.formal_questions] == ["Describe the API design."]
    assert [item.question for item in report.ambiguity_followups] == ["Clarify the ambiguous API ownership."]
