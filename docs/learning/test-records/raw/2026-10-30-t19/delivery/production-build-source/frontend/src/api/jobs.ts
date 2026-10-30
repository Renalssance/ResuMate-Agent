import { request } from '../services/request'
import { waitForTaskResult, type AcceptedTask } from '../services/taskResult'
import type { BackendDocumentParseResult } from './documents'
export interface Job {
  id: number; title: string; company: string | null; sourceUrl: string | null; sourceSite: string | null; sourceJobId: string | null
  capturedAt: string | null; status: 'saved' | 'archived'; primaryResumeId: number | null; parseStatus: string; createdAt: string; updatedAt: string
}
export interface JobDetail extends Job { text: string; structuredContent: Record<string, unknown> | null; primaryResume: { id: number; filename: string } | null }
export interface CaptureJob { title: string; company?: string; text: string; sourceUrl?: string }
export interface JobMatch { runId: string; candidateId: string; resumeId: number | null; score: number; createdAt: string }
export function fetchJobs(params: { query: string; status: string; offset: number }) { return request.get<{ items: Job[]; hasMore: boolean }, { items: Job[]; hasMore: boolean }>('/jobs', { params: { ...params, status: params.status || undefined, limit: 20 } }) }
export function captureJob(payload: CaptureJob) { return request.post<{ job: JobDetail; created: boolean }, { job: JobDetail; created: boolean }>('/jobs', payload) }
export function fetchJob(id: number) { return request.get<JobDetail, JobDetail>(`/jobs/${id}`) }
export function updateJob(id: number, payload: { title: string; company: string; status: string; primaryResumeId: number | null }) { return request.patch<JobDetail, JobDetail>(`/jobs/${id}`, payload) }
export function fetchJobMatches(id: number, offset = 0) { return request.get<{ items: JobMatch[]; hasMore: boolean }, { items: JobMatch[]; hasMore: boolean }>(`/jobs/${id}/matches`, { params: { limit: 20, offset } }) }
export async function parseJob(id: number, onAccepted: (taskId: string) => void) {
 const accepted = await request.post<AcceptedTask, AcceptedTask>(`/jobs/${id}/parse`)
 onAccepted(accepted.taskId)
 return waitForTaskResult(accepted.taskId, data => data.document as BackendDocumentParseResult)
}
