from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import (
    AnalysisCandidate,
    AnalysisJob,
    FollowUpQuestionSet,
    InterviewQuestionSet,
    JobDescription,
    MatchResult,
    Resume,
)
from backend.schemas.workflow import CandidateReport, CandidateSummary, QuestionSet, RunSummary


class SqlAlchemyRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, *, user_id: int, jd: JobDescription, resumes: list[Resume]) -> AnalysisJob:
        job = AnalysisJob(user_id=user_id, jd_id=jd.id, title=jd.title, status="running")
        self.db.add(job)
        self.db.flush()
        for resume in resumes:
            self.db.add(AnalysisCandidate(job_id=job.id, resume_id=resume.id, status="pending"))
        self.db.commit()
        self.db.refresh(job)
        return job

    def list_runs(self, *, user_id: int) -> list[RunSummary]:
        jobs = (
            self.db.query(AnalysisJob)
            .filter(AnalysisJob.user_id == user_id)
            .order_by(AnalysisJob.created_at.desc())
            .all()
        )
        return [self._summary(job) for job in jobs]

    def get_run(self, *, user_id: int, run_id: int) -> RunSummary | None:
        job = self._job(user_id, run_id)
        return self._summary(job) if job else None

    def get_candidate_report(self, *, user_id: int, run_id: int, candidate_id: int) -> CandidateReport | None:
        job = self._job(user_id, run_id)
        if not job:
            return None
        result = (
            self.db.query(MatchResult)
            .filter(MatchResult.job_id == job.id, MatchResult.candidate_id == candidate_id)
            .first()
        )
        if not result or not result.report_json:
            return None
        report = CandidateReport.model_validate(result.report_json)
        candidate = result.candidate
        updates = {}
        if candidate and candidate.question_set and candidate.question_set.questions:
            updates["formal_questions"] = candidate.question_set.questions
        if candidate and candidate.follow_up_set and candidate.follow_up_set.questions:
            updates["ambiguity_followups"] = candidate.follow_up_set.questions
        if not updates:
            return report
        return CandidateReport.model_validate({**report.model_dump(mode="json"), **updates})

    def get_candidate_resume_id(self, *, user_id: int, run_id: int, candidate_id: int) -> int | None:
        job = self._job(user_id, run_id)
        if not job:
            return None
        candidate = (
            self.db.query(AnalysisCandidate)
            .filter(AnalysisCandidate.job_id == job.id, AnalysisCandidate.id == candidate_id)
            .first()
        )
        return candidate.resume_id if candidate else None

    def save_report(self, *, job: AnalysisJob, candidate: AnalysisCandidate, report: CandidateReport) -> None:
        result = candidate.match_result or MatchResult(
            job_id=job.id,
            candidate_id=candidate.id,
            resume_id=candidate.resume_id,
            jd_id=job.jd_id,
        )
        result.overall_score = report.total_score
        result.recommendation = report.recommendation
        result.reason = report.summary
        result.dimension_scores = {item.name: item.score for item in report.evaluations}
        result.strengths = report.top_strengths
        result.gaps = [gap for item in report.evaluations for gap in item.missing_evidence]
        result.report_json = report.model_dump(mode="json")
        self.db.add(result)
        candidate.status = "completed"
        if all(item.status == "completed" for item in job.candidates):
            job.status = "completed"
        self.db.commit()

    def save_questions(
        self,
        *,
        user_id: int,
        run_id: int,
        candidate_id: int,
        question_set: QuestionSet,
    ) -> CandidateReport:
        job = self._job(user_id, run_id)
        if not job:
            raise ValueError("run not found")
        candidate = (
            self.db.query(AnalysisCandidate)
            .filter(AnalysisCandidate.job_id == job.id, AnalysisCandidate.id == candidate_id)
            .first()
        )
        if not candidate or not candidate.match_result or not candidate.match_result.report_json:
            raise ValueError("candidate report not found")

        stored_report = CandidateReport.model_validate(candidate.match_result.report_json)
        warnings = list(stored_report.warnings)
        if not any(item.evidence_chunk_ids for item in stored_report.evaluations):
            warning = "未找到可用于引用的简历证据，已保存面试题，但题目依据可能不完整。"
            if warning not in warnings:
                warnings.append(warning)
        report = stored_report.model_copy(
            update={
                "formal_questions": question_set.formal_questions,
                "ambiguity_followups": question_set.ambiguity_followups,
                "warnings": warnings,
            }
        )
        candidate.match_result.report_json = report.model_dump(mode="json")

        formal = candidate.question_set or InterviewQuestionSet(
            job_id=job.id, candidate_id=candidate.id, resume_id=candidate.resume_id, jd_id=job.jd_id,
        )
        formal.questions = [item.model_dump(mode="json") for item in question_set.formal_questions]
        followups = candidate.follow_up_set or FollowUpQuestionSet(
            job_id=job.id, candidate_id=candidate.id, resume_id=candidate.resume_id, jd_id=job.jd_id,
        )
        followups.questions = [item.model_dump(mode="json") for item in question_set.ambiguity_followups]
        self.db.add_all([candidate.match_result, formal, followups])
        self.db.commit()
        return report

    def mark_candidate_failed(self, candidate: AnalysisCandidate, detail: str) -> None:
        candidate.status = "failed"
        candidate.note = detail[:2000]
        self.db.commit()

    def delete_candidate(self, *, user_id: int, run_id: int, candidate_id: int) -> bool:
        job = self._job(user_id, run_id)
        if not job:
            return False
        candidate = (
            self.db.query(AnalysisCandidate)
            .filter(AnalysisCandidate.job_id == job.id, AnalysisCandidate.id == candidate_id)
            .first()
        )
        if not candidate:
            return False
        self.db.delete(candidate)
        self.db.commit()
        return True

    def _job(self, user_id: int, run_id: int) -> AnalysisJob | None:
        return (
            self.db.query(AnalysisJob)
            .filter(AnalysisJob.id == run_id, AnalysisJob.user_id == user_id)
            .first()
        )

    @staticmethod
    def _summary(job: AnalysisJob) -> RunSummary:
        candidates = []
        for candidate in job.candidates:
            result = candidate.match_result
            resume = candidate.resume
            if not result:
                continue
            candidates.append(
                CandidateSummary(
                    candidate_id=candidate.id,
                    candidate_name=str((resume.structured_data or {}).get("candidate_name") or (resume.structured_data or {}).get("name") or resume.filename),
                    filename=resume.filename,
                    total_score=result.overall_score,
                    recommendation=result.recommendation,
                    top_strengths=result.strengths[:3],
                )
            )
        candidates.sort(key=lambda item: item.total_score, reverse=True)
        return RunSummary(run_id=job.id, job_title=job.jd.title if job.jd else job.title, candidates=candidates)
