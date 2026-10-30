import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BusinessMemory from './BusinessMemory.vue'
const fixtures = vi.hoisted(() => ({ auth: { token: 'a' }, request: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => fixtures.auth }))
vi.mock('../services/request', () => ({ request: fixtures.request }))
const memory = { id: 'm1', kind: 'preference', content: '希望突出后端工程方向', sourceRef: { kind: 'manual' }, confirmedAt: '2026-10-30T00:00:00Z', createdAt: '2026-10-30T00:00:00Z' }
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(b => b.text() === text)!
async function openMemory() { const w = mount(BusinessMemory); await flushPromises(); return w }
beforeEach(() => {
 vi.resetAllMocks(); fixtures.auth = reactive({ token: 'a' })
 fixtures.request.get.mockResolvedValue({ items: [], pendingDeletions: [] })
 fixtures.request.post.mockResolvedValue(memory)
 fixtures.request.delete.mockResolvedValue({ memoryId: 'm1', cleanupStatus: 'complete', affectedRunIds: [], newSessionRequired: false })
})
describe('user confirmed business memory', () => {
 it('requires explicit confirmation and displays the saved content with its manual source', async () => {
  const w = await openMemory(); expect(w.text()).toContain('记忆不能作为经历证据')
  await w.get('textarea').setValue(memory.content); await w.get('form').trigger('submit'); await flushPromises()
  expect(fixtures.request.post).not.toHaveBeenCalled(); expect(button(w, '保存记忆').attributes('disabled')).toBeDefined()
  await w.get('input[data-memory-confirm]').setValue(true); await w.get('form').trigger('submit'); await flushPromises()
  expect(fixtures.request.post).toHaveBeenCalledWith('/memories', { kind: 'preference', content: memory.content, confirmed: true })
  expect(w.get('.memory-item').text()).toContain(memory.content); expect(w.get('.memory-item').text()).toContain('手动确认'); expect(w.get('textarea').element.value).toBe(''); w.unmount()
 })
 it('keeps the draft when saving loses its connection', async () => {
  fixtures.request.post.mockRejectedValue(new Error('Network Error'))
  const w = await openMemory(); await w.get('select').setValue('interview_feedback'); await w.get('textarea').setValue('回答要先说明我的职责'); await w.get('input[data-memory-confirm]').setValue(true); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('textarea').element.value).toBe('回答要先说明我的职责'); expect(w.get('select').element.value).toBe('interview_feedback'); expect(w.get('[role="alert"]').text()).toContain('网络连接中断'); w.unmount()
 })
 it('removes deleted content immediately but keeps pending cleanup visible until refreshed', async () => {
  fixtures.request.get.mockResolvedValueOnce({ items: [memory], pendingDeletions: [] }).mockResolvedValue({ items: [], pendingDeletions: [] })
  fixtures.request.delete.mockResolvedValue({ memoryId: 'm1', cleanupStatus: 'pending', affectedRunIds: ['r1'], newSessionRequired: true })
  const w = await openMemory(); await button(w, '删除记忆').trigger('click'); await flushPromises()
  expect(w.text()).not.toContain(memory.content); expect(w.get('.memory-pending').text()).toContain('任务副本仍在清理'); expect(w.text()).toContain('旧会话不能恢复'); expect(w.text()).not.toContain('清理完成')
  await button(w, '刷新记忆状态').trigger('click'); await flushPromises(); expect(w.find('.memory-pending').exists()).toBe(false); w.unmount()
 })
 it('does not resurrect a deleted memory when an older list request arrives late', async () => {
  let resolveOld!: (value: unknown) => void
  fixtures.request.get.mockResolvedValueOnce({ items: [memory], pendingDeletions: [] }).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
  const w = await openMemory(); await button(w, '刷新记忆状态').trigger('click'); await button(w, '删除记忆').trigger('click'); await flushPromises()
  resolveOld({ items: [memory], pendingDeletions: [] }); await flushPromises(); expect(w.text()).not.toContain(memory.content); w.unmount()
 })
 it('shows pending deletion returned after reopening without restoring its content', async () => {
  fixtures.request.get.mockResolvedValue({ items: [], pendingDeletions: [{ memoryId: 'm1', affectedRunIds: ['r1'], cleanupStatus: 'pending' }] })
  const w = await openMemory(); expect(w.get('.memory-pending').text()).toContain('任务副本仍在清理'); expect(w.find('.memory-item').exists()).toBe(false); expect(w.text()).toContain('原始面试记录仍保留'); w.unmount()
 })
 it('clears private state on account change and ignores the old account response', async () => {
  let resolveOld!: (value: unknown) => void
  fixtures.request.get.mockResolvedValueOnce({ items: [memory], pendingDeletions: [] }).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValue({ items: [], pendingDeletions: [] })
  const w = await openMemory(); await w.get('textarea').setValue('尚未保存的私人内容'); await button(w, '刷新记忆状态').trigger('click'); fixtures.auth.token = 'b'; await flushPromises()
  resolveOld({ items: [memory], pendingDeletions: [] }); await flushPromises(); expect(w.text()).not.toContain(memory.content); expect(w.get('textarea').element.value).toBe(''); w.unmount()
 })
})

it('waits for the initial list before saving so existing memories and pending cleanup stay visible', async () => {
 let resolveInitial!: (value: unknown) => void
 fixtures.request.get.mockImplementationOnce(() => new Promise(resolve => { resolveInitial = resolve }))
 fixtures.request.post.mockResolvedValue({ ...memory, id: 'm2', content: '下一次想补充的偏好' })
 const w = mount(BusinessMemory)
 await w.get('textarea').setValue('下一次想补充的偏好'); await w.get('input[data-memory-confirm]').setValue(true)
 expect(button(w, '保存记忆').attributes('disabled')).toBeDefined()
 await w.get('form').trigger('submit'); await flushPromises(); expect(fixtures.request.post).not.toHaveBeenCalled()
 resolveInitial({ items: [memory], pendingDeletions: [{ memoryId: 'deleted-memory', affectedRunIds: ['r1'], cleanupStatus: 'pending' }] }); await flushPromises()
 expect(w.get('.memory-item').text()).toContain(memory.content); expect(w.get('.memory-pending').text()).toContain('任务副本仍在清理')
 await w.get('form').trigger('submit'); await flushPromises()
 expect(w.findAll('.memory-item')).toHaveLength(2); expect(w.text()).toContain(memory.content); expect(w.text()).toContain('下一次想补充的偏好'); expect(w.get('.memory-pending').text()).toContain('任务副本仍在清理'); w.unmount()
})
