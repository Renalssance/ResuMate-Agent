import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, afterEach } from 'vitest'
import ModelCallsView from './ModelCallsView.vue'
const api = vi.hoisted(() => ({ fetchModelCalls: vi.fn(), fetchModelCall: vi.fn() }))
vi.mock('../api/llmCalls', () => api)
afterEach(() => vi.clearAllMocks())
describe('model call inspection', () => {
  it('opens the selected call and distinguishes unknown usage from zero', async () => {
    const row = { id: 1, task: 'document.parse_resume', model: 'test', base_url: 'https://model.test', attempt: 1, status: 'failed', usage: null, elapsed_ms: 1234, called_at: '2026-11-02T01:00:00Z' }
    api.fetchModelCalls.mockResolvedValue({ total: 1, items: [row] })
    api.fetchModelCall.mockResolvedValue({ ...row, request: { model: 'test', reasoning_effort: 'none', messages: [{ role: 'user', content: 'Skills: Python' }] }, output: { content: 'partial' }, error: 'APIConnectionError' })
    const wrapper = mount(ModelCallsView)
    await flushPromises()
    expect(wrapper.text()).toContain('— / —')
    await wrapper.get('[aria-label="查看调用 1"]').trigger('click'); await flushPromises()
    expect(wrapper.get('pre').text()).toContain('partial')
    const tabs = wrapper.findAll('[role="tab"]')
    await tabs[0]!.trigger('click'); expect(wrapper.get('pre').text()).toContain('none')
    await tabs[1]!.trigger('click'); expect(wrapper.get('pre').text()).toContain('Skills: Python')
    await tabs[3]!.trigger('click'); expect(wrapper.text()).toContain('接口未返回 Token 用量')
    wrapper.unmount()
  })
})
