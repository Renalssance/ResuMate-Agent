export interface ConversationRound {
  id: string
  question: string
  answer: string
  followUp: string
  reason: string
  evidence: string[]
  risks: string[]
}

export interface FollowUpSession {
  id: string
  jdId: string
  resumeId: string
  questionSetId?: string
  currentAbility: string
  coveredQuestions: string[]
  nextSuggestion: string
  rounds: ConversationRound[]
}
