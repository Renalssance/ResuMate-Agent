import { request } from '../services/request'
import type { BusinessMemory, MemoryDeletion, MemoryKind, MemoryList } from '../types/memory'

export function fetchMemories() {
  return request.get<MemoryList, MemoryList>('/memories')
}

export function saveMemory(payload: { kind: MemoryKind; content: string; confirmed: true }) {
  return request.post<BusinessMemory, BusinessMemory>('/memories', payload)
}

export function deleteMemory(id: string) {
  return request.delete<MemoryDeletion, MemoryDeletion>(`/memories/${encodeURIComponent(id)}`)
}
