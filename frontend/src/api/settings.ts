import { request } from '../services/request'
import type { LlmSettingsPayload, LlmSettingsResponse, LlmUsageDashboard } from '../types/settings'

export function fetchLlmSettingsApi() {
  return request.get<LlmSettingsResponse, LlmSettingsResponse>('/settings/llm')
}

export function saveLlmSettingsApi(payload: LlmSettingsPayload) {
  return request.put<LlmSettingsResponse, LlmSettingsResponse>('/settings/llm', payload)
}

export function fetchLlmUsageApi() {
  return request.get<LlmUsageDashboard, LlmUsageDashboard>('/settings/usage')
}
