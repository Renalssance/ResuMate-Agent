import { buildAuthHeaders } from '../services/authToken'
import type { RunSnapshot, RunStatus } from '../services/agentStream'

export type RunAction = RunSnapshot['actions'][number]
export interface AgentRunItem {
  runId: string; sessionId: string; kind: string; status: RunStatus
  createdAt: string; updatedAt: string; input: Record<string, unknown>; errorCode: string | null
}
export type ArtifactReference =
  | { kind: 'resume'; resumeId: number; inputVersion: string; section: string; sourceRefs: unknown[] }
  | { kind: 'profile_fact'; factId: string; revision: number }
  | { kind: 'applicant_answer'; actionId: string }
export interface ArtifactSource { reference: ArtifactReference; label: string; content: unknown }
export type ReviewStatus = 'pending' | 'accepted' | 'rejected' | 'edited'
export interface ReviewDecision { id: string; status: ReviewStatus; editedText?: string }
export interface TailoringChange {
  id: string; section: string; before: string; after: string | null; reason: string
  fact_refs: ArtifactReference[]; requires_input: boolean; status: ReviewStatus; editedText?: string
}
export interface ResumeVersionArtifact {
  kind?: 'resume_version'
  id: string; runId: string; resumeId: number; jdId: number; revision: number; status: string
  structuredContent: Record<string, unknown>; factRefs: unknown[]; createdAt: string
  reviewable?: boolean; sources?: ArtifactSource[]; basedOnOldInput?: boolean; changedInputs?: string[]
}
export interface ResumePdfArtifact {
  kind: 'resume_pdf'; id: string; runId: string; resumeVersionId: string; revision: number
  filename: string; downloadUrl: string; createdAt: string
}
export type RunArtifact = ResumeVersionArtifact | ResumePdfArtifact
export type CreateAgentRun =
  | { kind: 'tailoring'; jdId: number; resumeId: number; requestId: string }
  | { kind: 'resume_export'; resumeVersionId: string; requestId: string }

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

export async function downloadResumePdf(runId: string): Promise<Blob> {
  const response = await fetch(`/api/agent/runs${runPath(runId)}/download`, { headers: { ...buildAuthHeaders(), Accept: 'application/pdf' } })
  if (!response.ok) {
    const data = await response.json()
    throw new AgentRunError(response.status, data.code || 'request_failed', data.message || data.detail || '下载失败，请重试')
  }
  return response.blob()
}
export function taskStatusLabel(status: RunStatus, kind?: string) {
  const title = ({ document_parse: '解析', document_import: '导入', match_analysis: '匹配', question_generation: '出题', answer_followup: '回答分析' } as Record<string, string>)[kind || '']
  if (title) return ({ queued: `等待${title}`, running: `正在${title}`, succeeded: `${title}已完成`, failed: `${title}未完成`, cancelled: `${title}已取消` } as Partial<Record<RunStatus, string>>)[status] || runStatusLabel[status]
  if (kind !== 'resume_export') return runStatusLabel[status]
  return ({ queued: '等待导出', running: '正在导出 PDF', succeeded: 'PDF 已导出', failed: 'PDF 导出失败', cancelled: '导出已取消' } as Partial<Record<RunStatus, string>>)[status] || runStatusLabel[status]
}
