import { buildAuthHeaders } from '../services/authToken'
import { AgentRunError } from './agentRuns'
import type { RunStatus } from '../services/agentStream'
import type { RunAccepted } from './agentRuns'

export interface ChatSession {
  sessionId: string; title: string; createdAt: string; updatedAt: string; activeRunId: string | null
}
export interface ChatTool {
  name: string; operationKey: string; status: 'running' | 'succeeded' | 'failed'; resultRef: string | null
}
export interface AttachmentProgress {
  stage: string; message: string; createdAt: string; seq?: number
  current?: number | null; total?: number | null
  data: { scope: string; reset?: boolean; kind?: string | null; agent?: { phase: string; attempt: number } }
}
export interface ChatTurn {
  attachmentProgress?: AttachmentProgress[]
  reasoning?: string; reasoningActive?: boolean
  input?: { resumeId?: number | null; jdId?: number | null; attachment?: { filename: string } }
  runId: string; message: string; status: RunStatus; text: string; lastSeq: number; tools: ChatTool[]
  outputRefs: { type: string; id: string | number }[]; result: { text: string } | null; errorCode: string | null
}
export interface ChatDetail extends ChatSession { turns: ChatTurn[] }
export interface ChatMessage { message: string; requestId: string; resumeId?: number; jdId?: number }
async function chatRequest<T>(path = '', body?: unknown): Promise<T> {
  const response = await fetch(`/api/chat/sessions${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { ...buildAuthHeaders(), Accept: 'application/json', ...(body === undefined || body instanceof FormData ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: body instanceof FormData ? body : JSON.stringify(body) }),
  })
  const data = await response.json()
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item: { msg: string }) => item.msg).join('；') : data.detail
    throw new AgentRunError(response.status, data.code || 'request_failed', data.message || detail || '会话请求失败，请重试')
  }
  return data as T
}
const path = (id: string) => `/${encodeURIComponent(id)}`
export const fetchChatSessions = () => chatRequest<ChatSession[]>()
export const createChatSession = () => chatRequest<ChatSession>('', {})
export const fetchChatSession = (id: string) => chatRequest<ChatDetail>(path(id))
export const sendChatMessage = (id: string, payload: ChatMessage, file?: File) => {
  if (!file) return chatRequest<RunAccepted>(`${path(id)}/messages`, payload)
  const body = new FormData()
  for (const [key, value] of Object.entries(payload)) body.append(key, String(value))
  body.append('file', file)
  return chatRequest<RunAccepted>(`${path(id)}/messages/upload`, body)
}
