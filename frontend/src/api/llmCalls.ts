import { request } from '../services/request'
export interface ModelCall {
  id: number; task: string; model: string; base_url: string; attempt: number
  status: string; usage: Record<string, unknown> | null; elapsed_ms: number; called_at: string
}
export interface ModelCallDetail extends ModelCall {
  request: Record<string, unknown>; output: Record<string, unknown> | null; error: string
}
export function fetchModelCalls(offset = 0) {
  return request.get<never, { total: number; items: ModelCall[] }>('/settings/calls', { params: { offset, limit: 20 } })
}
export function fetchModelCall(id: number) {
  return request.get<never, ModelCallDetail>(`/settings/calls/${id}`)
}
