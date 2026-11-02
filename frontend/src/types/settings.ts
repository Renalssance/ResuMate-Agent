export interface LlmSettingsResponse {
  api_key: string
  has_api_key: boolean
  api_key_hint: string
  base_url: string
  model: string
  max_tokens: number
  context_window_tokens: number | null
  request_timeout_seconds: number
}

export interface LlmSettingsPayload {
  api_key?: string
  base_url?: string
  model?: string
  max_tokens?: number
  context_window_tokens?: number | null
  request_timeout_seconds?: number
}

export interface LlmUsageDailyPoint {
  date: string
  calls: number
  total_tokens: number
}

export interface LlmUsageTaskPoint {
  task: string
  calls: number
  total_tokens: number
}

export interface LlmUsageCall {
  id: number
  task: string
  model: string
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  success: boolean
  error_type: string
  elapsed_ms: number
  called_at: string
}

export interface LlmUsageDashboard {
  total_calls: number
  successful_calls: number
  failed_calls: number
  success_rate: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  last_called_at: string | null
  daily: LlmUsageDailyPoint[]
  by_task: LlmUsageTaskPoint[]
  recent_calls: LlmUsageCall[]
}

export interface EmbeddingSettingsResponse {
  api_key: string
  provider: 'openai' | 'qwen' | 'local'
  has_api_key: boolean
  api_key_hint: string
  base_url: string
  model: string
  source: 'saved' | 'environment'
}
export interface EmbeddingSettingsPayload {
  provider: 'openai' | 'qwen' | 'local'
  api_key: string
  base_url: string
  model: string
}
