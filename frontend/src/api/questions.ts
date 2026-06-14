import { request } from '../services/request'
import type { QuestionSet } from '../types/question'

export interface CreateQuestionSetPayload {
  jobDocumentId: string
  resumeDocumentId: string
  matchId?: string
  questionCount: number
}

export function createQuestionSetApi(payload: CreateQuestionSetPayload) {
  return request.post<{ taskId: string }, { taskId: string }>('/question-sets', payload)
}

export function fetchQuestionSetsApi() {
  return request.get<QuestionSet[], QuestionSet[]>('/question-sets')
}

export function fetchQuestionSetApi(questionSetId: string) {
  return request.get<QuestionSet, QuestionSet>(`/question-sets/${questionSetId}`)
}

export function deleteQuestionSetApi(questionSetId: string) {
  return request.delete<void, void>(`/question-sets/${questionSetId}`)
}
