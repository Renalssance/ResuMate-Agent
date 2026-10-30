import { request } from '../services/request'
import type { MatchResult } from '../types/match'

export interface CreateMatchPayload {
  jobDocumentId: string
  resumeDocumentIds: string[]
}

export function createMatchApi(payload: CreateMatchPayload) {
  return request.post<{ taskId: string }, { taskId: string }>('/matches', payload)
}

export function fetchMatchesApi() {
  return request.get<MatchResult[], MatchResult[]>('/matches')
}

export function fetchMatchApi(matchId: string) {
  return request.get<MatchResult, MatchResult>(`/matches/${matchId}`)
}

export function deleteMatchApi(matchId: string) {
  return request.delete<void, void>(`/matches/${matchId}`)
}
