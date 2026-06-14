import { request } from '../services/request'
import type { FollowUpSession } from '../types/followUp'

export interface CreateFollowUpSessionPayload {
  jobDocumentId: string
  resumeDocumentId: string
  questionSetId?: string
  initialQuestion?: string
}

export interface SubmitAnswerPayload {
  answer: string
}

export interface AnalyzeFollowUpPayload {
  question: string
  answer: string
  jd_context: Record<string, unknown>
  resume_context: Record<string, unknown>
  question_context?: Record<string, unknown>
  history?: Record<string, unknown>[]
}

export interface AnalyzeFollowUpResponse {
  follow_up: string
  reason: string
  evidence: string[]
  risks: string[]
  current_ability: string
  next_suggestion: string
}

export function createFollowUpSessionApi(payload: CreateFollowUpSessionPayload) {
  return request.post<{ sessionId: string; taskId?: string }, { sessionId: string; taskId?: string }>(
    '/follow-up/sessions',
    payload,
  )
}

export function fetchFollowUpSessionApi(sessionId: string) {
  return request.get<FollowUpSession, FollowUpSession>(`/follow-up/sessions/${sessionId}`)
}

export function submitFollowUpAnswerApi(sessionId: string, payload: SubmitAnswerPayload) {
  return request.post<{ taskId: string }, { taskId: string }>(`/follow-up/sessions/${sessionId}/answers`, payload)
}

export function analyzeFollowUpApi(payload: AnalyzeFollowUpPayload) {
  return request.post<AnalyzeFollowUpResponse, AnalyzeFollowUpResponse>('/followups/analyze', payload)
}
