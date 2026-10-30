import type { ProgressStep, TaskStatus } from '../types/task'

export interface ProgressSegment {
  key: string
  label: string
  status: TaskStatus
  fillPercent: number
  title: string
}

export function buildProgressSegments(steps: ProgressStep[]): ProgressSegment[] {
  return steps.map((step) => {
    const fillPercent = segmentFillPercent(step)
    return {
      key: step.key,
      label: step.label,
      status: step.status,
      fillPercent,
      title: `${step.label} · ${fillPercent}%`,
    }
  })
}

function segmentFillPercent(step: ProgressStep) {
  if (step.status === 'success' || step.status === 'failed') return 100
  if (step.status === 'running') return clampPercent(step.progress)
  return 0
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}
