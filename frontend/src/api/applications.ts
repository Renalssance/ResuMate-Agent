import { request } from '../services/request'
import type {
  ApplicationStatusEventPayload,
  BackendJobApplicationRecord,
  JobApplicationPayload,
} from '../types/application'

export function fetchApplicationsApi() {
  return request.get<BackendJobApplicationRecord[], BackendJobApplicationRecord[]>('/applications')
}

export function createApplicationApi(payload: JobApplicationPayload) {
  return request.post<BackendJobApplicationRecord, BackendJobApplicationRecord>('/applications', payload)
}

export function updateApplicationApi(id: number, payload: Partial<JobApplicationPayload>) {
  return request.patch<BackendJobApplicationRecord, BackendJobApplicationRecord>(`/applications/${id}`, payload)
}

export function createApplicationStatusEventApi(id: number, payload: ApplicationStatusEventPayload) {
  return request.post<BackendJobApplicationRecord, BackendJobApplicationRecord>(
    `/applications/${id}/status-events`,
    payload,
  )
}

export function deleteApplicationApi(id: number) {
  return request.delete<{ id: number }, { id: number }>(`/applications/${id}`)
}
