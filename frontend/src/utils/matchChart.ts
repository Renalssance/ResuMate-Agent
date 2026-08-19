import type { MatchCriterion } from '../types/match'

export interface CriterionChartRow extends MatchCriterion {
  scorePercent: number
  contribution: number
  tone: 'strong' | 'good' | 'weak'
}

export function clampScorePercent(score: number) {
  if (!Number.isFinite(score)) return 0
  return Math.max(0, Math.min(100, Math.round(score)))
}

export function buildCriterionChartRows(criteria: MatchCriterion[]): CriterionChartRow[] {
  return criteria
    .map((item, index) => ({
      ...item,
      scorePercent: clampScorePercent((item.score / 5) * 100),
      contribution: roundOne(item.weight * item.score / 5),
      tone: criterionTone(item.score),
      index,
    }))
    .sort((a, b) => b.contribution - a.contribution || a.index - b.index)
}

function criterionTone(score: number): CriterionChartRow['tone'] {
  if (score >= 4) return 'strong'
  if (score >= 3) return 'good'
  return 'weak'
}

function roundOne(value: number) {
  return Math.round(value * 10) / 10
}
