export interface LlmSettingsResponse {
  has_api_key: boolean
  api_key_hint: string
  base_url: string
  model: string
  max_tokens: number
  request_timeout_seconds: number
}

export interface LlmSettingsPayload {
  api_key?: string
  clear_api_key?: boolean
  base_url?: string
  model?: string
  max_tokens?: number
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
