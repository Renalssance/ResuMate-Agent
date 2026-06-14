export interface MatchCriterion {
  name: string
  weight: number
  score: number
  reason: string
}

export interface MatchResult {
  id: string
  jdId: string
  jdTitle: string
  resumeId: string
  candidateName: string
  score: number
  conclusion: string
  strengths: string[]
  gaps: string[]
  risks: string[]
  summary: string
  criteria: MatchCriterion[]
  evidence: string[]
  agentContent: string
  logs: string[]
  createdAt: string
}
