import type { TaskStatus } from './task'

export type DocumentType = 'resume' | 'jd'

export interface DocumentRecord {
  id: string
  type: DocumentType
  filename: string
  size: number
  createdAt: string
  parseStatus: TaskStatus
  rawText?: string
  parsedContent?: Record<string, unknown>
  vectorized: boolean
  localStored: boolean
}
