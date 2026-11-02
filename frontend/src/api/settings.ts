import { request } from '../services/request'
import type { LlmSettingsPayload, LlmSettingsResponse, LlmUsageDashboard, EmbeddingSettingsResponse, EmbeddingSettingsPayload } from '../types/settings'

export function fetchLlmSettingsApi() {
  return request.get<LlmSettingsResponse, LlmSettingsResponse>('/settings/llm')
}

export function saveLlmSettingsApi(payload: LlmSettingsPayload) {
  return request.put<LlmSettingsResponse, LlmSettingsResponse>('/settings/llm', payload)
}

export function fetchLlmUsageApi() {
  return request.get<LlmUsageDashboard, LlmUsageDashboard>('/settings/usage')
}

export function fetchEmbeddingSettingsApi() {
  return request.get<EmbeddingSettingsResponse, EmbeddingSettingsResponse>('/settings/embedding')
}
export function saveEmbeddingSettingsApi(payload: EmbeddingSettingsPayload) {
  return request.put<EmbeddingSettingsResponse, EmbeddingSettingsResponse>('/settings/embedding', payload)
}
export function testEmbeddingSettingsApi() {
  return request.post<{ success: boolean; dimensions: number }, { success: boolean; dimensions: number }>('/settings/embedding/test')
}

export function testLlmSettingsApi() {
  return request.post<{ success: boolean }, { success: boolean }>('/settings/llm/test')
}
