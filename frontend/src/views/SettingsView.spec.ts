import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsView from './SettingsView.vue'
import { saveLlmSettingsApi } from '../api/settings'
const fixtures = vi.hoisted(() => ({ request: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('../components/EmbeddingSettingsCard.vue', () => ({ default: { template: '<section />' } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ token: 'token', isAuthenticated: true }) }))
vi.mock('../services/request', () => ({ request: fixtures.request }))
const settings = { api_key: 'saved-llm-key', has_api_key: true, api_key_hint: '•••', base_url: 'https://example.com/v1', model: 'custom-model', max_tokens: 8192, context_window_tokens: null, request_timeout_seconds: 300 }
const usage = { total_calls: 0, successful_calls: 0, failed_calls: 0, success_rate: 0, total_tokens: 0, prompt_tokens: 0, completion_tokens: 0, last_called_at: null, daily: [], by_task: [], recent_calls: [] }
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(b => b.text() === text)!
async function openSettings() {
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: SettingsView }] }); await router.push('/'); await router.isReady()
 const w = mount(SettingsView, { global: { plugins: [router] } }); await flushPromises(); return w
}
beforeEach(() => {
 vi.resetAllMocks()
 fixtures.request.get.mockImplementation((path: string) => Promise.resolve(path === '/settings/llm' ? { ...settings } : usage))
 fixtures.request.put.mockImplementation((_path: string, payload: object) => Promise.resolve({ ...settings, ...payload }))
})
describe('explicit model context capacity', () => {
 it('shows unknown capacity separately from the output limit without guessing from model name', async () => {
  const w = await openSettings(); const item = w.findAll('.model-field').find(item => item.text().includes('上下文容量'))
  expect(item?.find('input').attributes('placeholder')).toBe('未配置'); expect(w.text()).toContain('输出上限'); w.unmount()
 })
 it('saves a blank context capacity as null while keeping the other settings', async () => {
  const w = await openSettings(); await button(w, '编辑').trigger('click'); await w.get('#settings-context-window').setValue('32768'); await w.get('#settings-context-window').setValue('')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(fixtures.request.put).toHaveBeenCalledWith('/settings/llm', expect.objectContaining({ context_window_tokens: null, max_tokens: 8192, base_url: 'https://example.com/v1', model: 'custom-model' })); expect(w.text()).toContain('设置已保存'); w.unmount()
 })
 it('retains entered capacity and server validation when saving fails', async () => {
  fixtures.request.put.mockRejectedValue(Object.assign(new Error('上下文容量必须大于输出 Token 上限'), { status: 422 }))
  const w = await openSettings(); await button(w, '编辑').trigger('click'); await w.get('#settings-context-window').setValue('4096'); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get<HTMLInputElement>('#settings-context-window').element.value).toBe('4096'); expect(w.get('[role="alert"]').text()).toContain('上下文容量必须大于输出 Token 上限'); w.unmount()
 })
 it('does not clear unspecified fields when saving a partial capacity update', async () => {
  await saveLlmSettingsApi({ context_window_tokens: 32768 }); expect(fixtures.request.put).toHaveBeenCalledWith('/settings/llm', { context_window_tokens: 32768 })
 })
})

describe('chat usage', () => {
 it('shows chat consumption in totals, task distribution and recent calls', async () => {
  const chatUsage = { ...usage, total_calls: 1, successful_calls: 1, total_tokens: 1500,
   prompt_tokens: 1000, completion_tokens: 500,
   by_task: [{ task: 'chat', calls: 1, total_tokens: 1500 }],
   recent_calls: [{ id: 1, task: 'chat', model: 'test-model', total_tokens: 1500,
    elapsed_ms: 50, success: true, called_at: '2026-10-31T10:00:00Z' }] }
  fixtures.request.get.mockImplementation((path: string) => Promise.resolve(path === '/settings/llm' ? settings : chatUsage))
  const w = await openSettings()
  expect(w.text()).toContain('1,500')
  expect(w.get('.usage-task-row').text()).toContain('聊天')
  expect(w.get('.usage-task-row').text()).toContain('1,500 token')
  expect(w.get('.settings-usage-table tbody').text()).toContain('聊天')
  expect(w.get('.settings-usage-table tbody').text()).toContain('1,500')
  w.unmount()
 })
})


it('edits in place, displays the saved key and tests only saved configuration', async () => {
 fixtures.request.post.mockResolvedValue({ success: true })
 const w = await openSettings()
 expect(w.get<HTMLInputElement>('#settings-api-key').element.value).toBe('saved-llm-key')
 expect(w.get('#settings-api-key').attributes('readonly')).toBeDefined()
 expect(w.text()).not.toContain('清空已保存')
 await button(w, '编辑').trigger('click')
 expect(w.get('#settings-api-key').attributes('readonly')).toBeUndefined()
 await w.get('#settings-api-key').setValue('updated-key')
 await button(w, '测试').trigger('click'); await flushPromises()
 expect(fixtures.request.post).toHaveBeenCalledWith('/settings/llm/test')
 expect(w.text()).toContain('连接成功')
 await w.get('form').trigger('submit'); await flushPromises()
 expect(fixtures.request.put).toHaveBeenCalledWith('/settings/llm', expect.objectContaining({ api_key: 'updated-key' }))
 expect(w.get<HTMLInputElement>('#settings-api-key').element.value).toBe('updated-key')
 expect(w.get('#settings-api-key').attributes('readonly')).toBeDefined()
 w.unmount()
})
