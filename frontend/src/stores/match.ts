import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createRunApi, deleteCandidateReportApi, fetchCandidateReportApi, fetchRunsApi } from '../api/runs'
import type { DocumentRecord } from '../types/document'
import type { MatchResult } from '../types/match'
import type { CandidateReport } from '../types/run'
import { reportToMatch } from './matchMapping'

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
