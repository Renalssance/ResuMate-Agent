export type MemoryKind = 'preference' | 'interview_feedback'

export interface BusinessMemory {
  id: string
  kind: MemoryKind
  content: string
  sourceRef: { kind: 'manual' } | { kind: 'interview_turn'; interviewId: string; turnId: number }
  confirmedAt: string
  createdAt: string
}

export interface PendingMemoryDeletion {
  memoryId: string
  affectedRunIds: string[]
  cleanupStatus: 'pending'
}

export interface MemoryList {
  items: BusinessMemory[]
  pendingDeletions: PendingMemoryDeletion[]
}

export interface MemoryDeletion {
  memoryId: string
  cleanupStatus: 'pending' | 'complete'
  affectedRunIds: string[]
  newSessionRequired: boolean
}
