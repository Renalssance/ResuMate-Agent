import { buildAuthHeaders } from '../services/authToken'
import type { RunSnapshot, RunStatus } from '../services/agentStream'

export type RunAction = RunSnapshot['actions'][number]
export interface AgentRunItem {
  runId: string; sessionId: string; kind: string; status: RunStatus
  createdAt: string; updatedAt: string; input: Record<string, unknown>; errorCode: string | null
}
export interface RunArtifact {
  id: string; runId: string; resumeId: number; jdId: number; revision: number; status: string
  structuredContent: Record<string, unknown>; factRefs: unknown[]; createdAt: string
}
export interface CreateAgentRun { kind: 'tailoring'; jdId: number; resumeId: number; requestId: string }
export interface ActionAnswer { decision: 'submit' | 'approve' | 'reject'; answers: Record<string, string>; expectedRevision: number }
export interface RunAccepted { runId: string; status: RunStatus }
export class AgentRunError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); this.name = 'AgentRunError' }
}
async function runRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/agent/runs${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { ...buildAuthHeaders(), Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const data = await response.json()
  if (!response.ok) throw new AgentRunError(response.status, data.code || 'request_failed', data.message || '请求失败，请重试')
  return data as T
}
const runPath = (id: string) => `/${encodeURIComponent(id)}`
export const fetchAgentRuns = (offset = 0) => runRequest<{ items: AgentRunItem[]; hasMore: boolean }>(`?limit=20&offset=${offset}`)
export const fetchAgentRun = (id: string) => runRequest<RunSnapshot>(runPath(id))
export const fetchRunArtifacts = (id: string) => runRequest<RunArtifact[]>(`${runPath(id)}/artifacts`)
export const createAgentRun = (payload: CreateAgentRun) => runRequest<RunAccepted>('', payload)
export const answerRunAction = (id: string, actionId: string, answer: ActionAnswer) => runRequest<RunAccepted>(`${runPath(id)}/actions/${encodeURIComponent(actionId)}`, answer)
export const cancelAgentRun = (id: string) => runRequest<RunAccepted>(`${runPath(id)}/cancel`, {})
export const retryAgentRun = (id: string) => runRequest<RunAccepted>(`${runPath(id)}/retry`, {})
export const runStatusLabel: Record<RunStatus, string> = {
  queued: '等待开始', running: '正在准备', waiting_input: '等待你补充信息', waiting_approval: '等待你审阅',
  succeeded: '材料已生成', failed: '任务失败', cancelled: '任务已取消',
}
