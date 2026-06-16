import { request } from '../services/request'
import type { CandidateReport, EvidenceSearchResponse, RunSummary } from '../types/run'

export interface CreateRunPayload {
  jd_document_id: string
  resume_document_ids: string[]
  taskId?: string
}

export function createRunApi(payload: CreateRunPayload) {
  return request.post<RunSummary, RunSummary>('/runs', payload)
}

export function fetchRunsApi() {
  return request.get<RunSummary[], RunSummary[]>('/runs')
}

export function fetchCandidateReportApi(runId: string | number, candidateId: string | number) {
  return request.get<CandidateReport, CandidateReport>(`/runs/${runId}/candidates/${candidateId}`)
}

export function generateCandidateQuestionsApi(runId: string | number, candidateId: string | number, taskId = '', questionCount = 10) {
  const params = new URLSearchParams({ question_count: String(questionCount) })
  if (taskId) params.set('task_id', taskId)
  return request.post<CandidateReport, CandidateReport>(`/runs/${runId}/candidates/${candidateId}/questions?${params.toString()}`)
}

export function deleteCandidateReportApi(runId: string | number, candidateId: string | number) {
  return request.delete<void, void>(`/runs/${runId}/candidates/${candidateId}`)
}

export function searchEvidenceApi(runId: string | number, candidateId: string | number, query: string, topK = 4) {
  return request.post<EvidenceSearchResponse, EvidenceSearchResponse>(
    `/runs/${runId}/candidates/${candidateId}/evidence/search`,
    { query, top_k: topK },
  )
}
