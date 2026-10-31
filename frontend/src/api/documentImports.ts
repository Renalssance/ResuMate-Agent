import { buildAuthHeaders } from '../services/authToken'
import type { RunAccepted } from './agentRuns'

export async function importLocalDocument(file: File, requestId: string): Promise<RunAccepted> {
  const body = new FormData()
  body.append('file', file)
  body.append('requestId', requestId)
  const response = await fetch('/api/documents/import', {
    method: 'POST', headers: buildAuthHeaders(), body,
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || '文件导入失败')
  return data as RunAccepted
}
