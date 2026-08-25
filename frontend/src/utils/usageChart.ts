import type { LlmUsageDailyPoint, LlmUsageTaskPoint } from '../types/settings'

export interface UsageDailyBar extends LlmUsageDailyPoint {
  tokenPercent: number
  callPercent: number
  label: string
}

export interface UsageTaskBar extends LlmUsageTaskPoint {
  percent: number
}

export function buildUsageDailyBars(points: LlmUsageDailyPoint[]): UsageDailyBar[] {
  const maxTokens = Math.max(1, ...points.map((item) => item.total_tokens))
  const maxCalls = Math.max(1, ...points.map((item) => item.calls))
  return points.map((item) => ({
    ...item,
    tokenPercent: clampPercent(item.total_tokens / maxTokens * 100),
    callPercent: clampPercent(item.calls / maxCalls * 100),
    label: item.date.slice(5),
  }))
}

export function buildUsageTaskBars(points: LlmUsageTaskPoint[]): UsageTaskBar[] {
  const maxTokens = Math.max(1, ...points.map((item) => item.total_tokens))
  return points.map((item) => ({
    ...item,
    percent: clampPercent(item.total_tokens / maxTokens * 100),
  }))
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}
