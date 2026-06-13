from __future__ import annotations

from dataclasses import dataclass, field

from backend.schemas.workflow import CandidateReport, CandidateSummary, RunSummary


@dataclass
class RunRecord:
    run_id: str
    job_title: str
    reports: dict[str, CandidateReport] = field(default_factory=dict)

    def summary(self) -> RunSummary:
        candidates = [
            CandidateSummary(
                candidate_id=report.candidate_id,
                candidate_name=report.candidate_name,
                filename=report.filename,
                total_score=report.total_score,
                recommendation=report.recommendation,
                top_strengths=report.top_strengths[:3],
            )
            for report in self.reports.values()
        ]
        candidates.sort(key=lambda item: item.total_score, reverse=True)
        return RunSummary(run_id=self.run_id, job_title=self.job_title, candidates=candidates)


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(self, run_id: str, job_title: str) -> RunRecord:
        record = RunRecord(run_id=run_id, job_title=job_title)
        self._runs[run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def save_report(self, run_id: str, report: CandidateReport) -> None:
        record = self._runs.get(run_id)
        if record is None:
            record = self.create(run_id, report.job_profile.job_title)
        record.job_title = report.job_profile.job_title
        record.reports[report.candidate_id] = report


run_repository = InMemoryRunRepository()
