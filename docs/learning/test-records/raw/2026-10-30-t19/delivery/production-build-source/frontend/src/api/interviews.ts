import { buildAuthHeaders } from '../services/authToken'
import { AgentRunError } from './agentRuns'
import type { BusinessMemory } from '../types/memory'
import type { InterviewAck, InterviewCommand, InterviewSnapshot } from '../types/interview'
async function interviewRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/interviews${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(15000),
    headers: { ...buildAuthHeaders(), Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const data = await response.json()
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item: { msg: string }) => item.msg).join('；') : data.detail
    throw new AgentRunError(response.status, data.code || 'request_failed', data.message || detail || '无法完成操作，请重试')
  }
  return data as T
}
const interviewPath = (id: string) => `/${encodeURIComponent(id)}`
export const createInterview = (applicationId: number, requestId: string) => interviewRequest<{ interviewId: string; runId: string }>('', { applicationId, requestId })
export const fetchInterview = (id: string) => interviewRequest<InterviewSnapshot>(interviewPath(id))
export const sendInterviewCommand = (id: string, command: InterviewCommand) => interviewRequest<InterviewAck>(`${interviewPath(id)}/commands`, command)
export const confirmInterviewMemory = (id: string, turn: number) => interviewRequest<BusinessMemory>(`${interviewPath(id)}/turns/${turn}/memory`, { confirmed: true })
