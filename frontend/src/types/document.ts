import type { TaskStatus } from './task'

export type DocumentType = 'resume' | 'jd'
export type DocumentParseStatus = TaskStatus | 'success_with_warnings'

export interface DocumentRecord {
  id: string
  type: DocumentType
  filename: string
  size: number
  createdAt: string
  parseStatus: DocumentParseStatus
  rawText?: string
  parsedContent?: Record<string, unknown>
  vectorized: boolean
  localStored: boolean
}
