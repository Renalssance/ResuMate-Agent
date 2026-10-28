import { request } from '../services/request'
import { waitForTaskResult, type AcceptedTask } from '../services/taskResult'
import type { CandidateReport, EvidenceSearchResponse, RunSummary } from '../types/run'

export interface CreateRunPayload {
  jd_document_id: string
  resume_document_ids: string[]
  taskId?: string
}

export async function createRunApi(payload: CreateRunPayload) {
  const accepted = await request.post<AcceptedTask, AcceptedTask>('/runs', payload, {
    headers: { Prefer: 'respond-async' },
  })
  return waitForTaskResult(accepted.taskId, (data) => data as unknown as RunSummary)
}

export function fetchRunsApi() {
  return request.get<RunSummary[], RunSummary[]>('/runs')
}

export function fetchCandidateReportApi(runId: string | number, candidateId: string | number) {
  return request.get<CandidateReport, CandidateReport>(`/runs/${runId}/candidates/${candidateId}`)
}

export async function generateCandidateQuestionsApi(runId: string | number, candidateId: string | number, taskId = '', questionCount = 10) {
  const params = new URLSearchParams({ question_count: String(questionCount) })
  if (taskId) params.set('task_id', taskId)
  const accepted = await request.post<AcceptedTask, AcceptedTask>(`/runs/${runId}/candidates/${candidateId}/questions?${params.toString()}`, undefined, {
    headers: { Prefer: 'respond-async' },
  })
  return waitForTaskResult(accepted.taskId, (data) => data as unknown as CandidateReport)
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
