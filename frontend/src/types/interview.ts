import type { RunStatus } from '../services/agentStream'
export interface InterviewRef {
  kind: 'resume' | 'job' | 'answer'; quote: string
  section?: string; resumeVersionId?: string; revision?: number; jdId?: number; turnIndex?: number; turnId?: number
}
export interface InterviewFeedback {
  summary: string; strengths: { text: string; refs: InterviewRef[] }[]
  improvements: { text: string; refs: InterviewRef[] }[]; practiceFocus: string; memoryId?: string | null
}
export interface InterviewTurn {
  id: number; turnIndex: number; question: string; answer: string | null
  questionContext: { mode: 'opening' | 'follow_up' | 'new_topic'; refs: InterviewRef[] } | null
  feedback: InterviewFeedback | null
}
export interface InterviewSnapshot {
  interviewId: string; userId: number; applicationId: number; status: 'active' | 'finished'
  currentTurn: number; lastSeq: number; sessionInvalidated: boolean
  sourceSnapshot: {
    applicationId: number; resumeVersionId: string; revision: number; submittedAt: string
    structuredContent: Record<string, unknown>; factRefs: unknown[]
    job: { jdId: number; title: string; company: string; rawText: string; structuredData: Record<string, unknown>; capturedAt: string }
  }
  turns: InterviewTurn[]
  generation: { runId: string; status: RunStatus; errorCode: string | null; cancelRequested: boolean } | null
}
export type InterviewCommand = { clientMessageId: string; expectedTurn: number } & (
  | { type: 'answer.submit'; payload: { text: string } }
  | { type: 'generation.cancel' | 'generation.retry'; payload: { runId: string } }
  | { type: 'session.finish'; payload: Record<string, never> }
)
export interface InterviewAck { interviewId: string; clientMessageId: string; status: 'accepted'; resultRef: string | null; acceptedSeq: number }
