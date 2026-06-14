import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createRunApi, deleteCandidateReportApi, fetchCandidateReportApi, fetchRunsApi } from '../api/runs'
import type { DocumentRecord } from '../types/document'
import type { MatchResult } from '../types/match'
import type { CandidateReport, CandidateSummary } from '../types/run'

const reportByMatchId = new Map<string, CandidateReport>()

export function getReportForMatch(matchId: string) {
  return reportByMatchId.get(matchId)
}

export const useMatchStore = defineStore('match', () => {
  const results = ref<MatchResult[]>([])
  const loading = ref(false)
  const error = ref('')

  async function loadMatches() {
    loading.value = true
    try {
      const runs = await fetchRunsApi()
      const loaded: MatchResult[] = []
      for (const run of runs) {
        for (const candidate of run.candidates) {
          const report = await fetchCandidateReportApi(run.run_id, candidate.candidate_id)
          const match = reportToMatch(String(run.run_id), candidate, report)
          reportByMatchId.set(match.id, report)
          loaded.push(match)
        }
      }
      results.value = loaded
      error.value = ''
    } finally {
      loading.value = false
    }
  }

  async function createMatch(jd: DocumentRecord, resumes: DocumentRecord[], taskId = '') {
    loading.value = true
    error.value = ''
    try {
      const created = await runAnalysis(jd, resumes, taskId)
      results.value = [...created, ...results.value]
      return { matchIds: created.map((match) => match.id) }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function runAnalysis(jd: DocumentRecord, resumes: DocumentRecord[], taskId = '') {
    const run = await createRunApi({
      jd_document_id: jd.id,
      resume_document_ids: resumes.map((resume) => resume.id),
      taskId,
    })
    const created: MatchResult[] = []
    for (const candidate of run.candidates) {
      const report = await fetchCandidateReportApi(run.run_id, candidate.candidate_id)
      const match = reportToMatch(String(run.run_id), candidate, report)
      reportByMatchId.set(match.id, report)
      created.push(match)
    }
    return created
  }

  async function deleteMatch(id: string) {
    const [runId, candidateId] = id.split(':')
    await deleteCandidateReportApi(runId, candidateId)
    reportByMatchId.delete(id)
    results.value = results.value.filter((result) => result.id !== id)
  }

  return { results, loading, error, loadMatches, createMatch, deleteMatch }
})

function reportToMatch(runId: string, candidate: CandidateSummary, report: CandidateReport): MatchResult {
  const id = `${runId}:${candidate.candidate_id}`
  const jobProfile = report.job_profile
  return {
    id,
    jdId: runId,
    jdTitle: jobProfile?.job_title || extractJobTitle(report.summary),
    resumeId: String(candidate.candidate_id),
    candidateName: candidate.candidate_name,
    score: candidate.total_score,
    conclusion: recommendationText(candidate.recommendation),
    strengths: candidate.top_strengths,
    gaps: report.evaluations.flatMap((item) => item.missing_evidence).slice(0, 3),
    risks: report.evaluations.map((item) => item.risk).filter(Boolean).slice(0, 3),
    summary: report.summary,
    criteria: report.evaluations.map((item) => ({
      name: item.name,
      weight: item.weight,
      score: item.score,
      reason: item.reason,
    })),
    evidence: report.evaluations.flatMap((item) =>
      item.evidence.map((evidence) => `${evidence.filename} p${evidence.page_number} ${evidence.section}: ${evidence.text}`),
    ),
    agentContent: report.summary,
    logs: [
      'Documents indexed in Milvus',
      'Evidence retrieved per JD criterion',
      'LLM evaluated criterion-level match',
      'Python calculated total score',
    ],
    createdAt: new Date().toISOString(),
  }
}

function extractJobTitle(summary: string) {
  return summary.split(' matched ')[1]?.split(' with score ')[0] || 'JD'
}

function recommendationText(value: string) {
  const map: Record<string, string> = {
    strong_recommend: 'Strong recommend',
    recommend: 'Recommend',
    hold: 'Hold',
    reject: 'Reject',
  }
  return map[value] || value
}
