import { buildAuthHeaders } from '../services/authToken'
import { AgentRunError, type ReviewDecision, type ResumeVersionArtifact, type RunAccepted } from './agentRuns'

async function versionRequest<T = ResumeVersionArtifact>(id: string, method = 'GET', body?: unknown, action = ''): Promise<T> {
  const path = `/api/resume-versions/${encodeURIComponent(id)}${action}`
  const response = await fetch(path, {
    method,
    headers: { ...buildAuthHeaders(), Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const data = await response.json()
  if (!response.ok) {
    const detail = data.detail
    const message = Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join('；') : detail
    throw new AgentRunError(response.status, data.code || 'request_failed', data.message || message || '请求失败，请重试')
  }
  return data as T
}
export const fetchResumeVersion = (id: string) => versionRequest(id)
export const saveResumeVersion = (id: string, expectedRevision: number, changes: ReviewDecision[]) => versionRequest(id, 'PATCH', { expectedRevision, changes })
export const confirmResumeVersion = (id: string, expectedRevision: number) => versionRequest(id, 'POST', { expectedRevision }, '/confirm')
export const exportResumeVersion = (id: string, requestId: string) => versionRequest<RunAccepted>(id, 'POST', { requestId }, '/export')
