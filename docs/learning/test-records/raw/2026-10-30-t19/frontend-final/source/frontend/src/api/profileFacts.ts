import { request } from '../services/request'
export interface ProfileFact { id: string; factKey: string; kind: 'preference' | 'experience'; content: Record<string, unknown> & { text: string }; sourceDocumentId: number | null; revision: number; confirmedAt: string | null; deletedAt: string | null }
export interface FactInput { kind: ProfileFact['kind']; content: ProfileFact['content']; sourceDocumentId?: number; confirmed: boolean }
export function fetchProfileFacts(sourceDocumentId?: number, includeDeleted = false) { return request.get<{ items: ProfileFact[] }, { items: ProfileFact[] }>('/profile-facts', { params: { sourceDocumentId, includeDeleted } }) }
export function createProfileFact(payload: FactInput) { return request.post<ProfileFact, ProfileFact>('/profile-facts', payload) }
export function updateProfileFact(id: string, payload: { expectedRevision: number; content: ProfileFact['content']; confirmed: boolean }) { return request.patch<ProfileFact, ProfileFact>(`/profile-facts/${encodeURIComponent(id)}`, payload) }
export function deleteProfileFact(id: string, expectedRevision: number) { return request.delete<ProfileFact, ProfileFact>(`/profile-facts/${encodeURIComponent(id)}`, { params: { expectedRevision } }) }
export function fetchFactHistory(id: string) { return request.get<{ items: ProfileFact[] }, { items: ProfileFact[] }>(`/profile-facts/${encodeURIComponent(id)}/history`) }
