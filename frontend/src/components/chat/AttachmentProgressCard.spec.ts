import { afterEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AttachmentProgressCard from './AttachmentProgressCard.vue'

afterEach(() => vi.useRealTimers())

it('keeps replaced stage summaries in event order', () => {
  const event = { stage: 'classify', message: '正在识别文件类型', createdAt: '2026-11-02T00:00:00Z', data: { scope: 'attachment' } }
  const wrapper = mount(AttachmentProgressCard, { props: { filename: '简历.pdf', status: 'running', events: [
    event,
    { ...event, message: '正在判断文件类型', data: { ...event.data, agent: { phase: 'waiting_response', attempt: 1 } } },
    { ...event, message: '已识别为简历' },
  ] } })
  expect(wrapper.get('.analysis-process li.latest').text()).toBe('已识别为简历')
  expect(wrapper.findAll('.analysis-process li')).toHaveLength(2)
  wrapper.unmount()
})

it('updates elapsed time without inventing progress, then stops the clock on completion', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-02T00:00:00Z'))
  const event = { stage: 'llm_analyze', message: '正在提取经历和技能', createdAt: '2026-11-02T00:00:00Z', data: { scope: 'attachment', kind: 'resume' } }
  const wrapper = mount(AttachmentProgressCard, { props: { filename: '简历.pdf', status: 'running', events: [event] } })
  await vi.advanceTimersByTimeAsync(32000)
  expect(wrapper.get('summary').text()).toContain('32 秒')
  expect(wrapper.get('[role="status"]').text()).toContain('仍在处理中')
  expect(wrapper.text()).not.toContain('%')
  expect(wrapper.findAll('.parse-stages .active')).toHaveLength(1)
  await wrapper.setProps({ events: [event, { ...event, stage: 'complete', createdAt: '2026-11-02T00:00:32Z' }] })
  await vi.advanceTimersByTimeAsync(5000)
  expect(wrapper.get('summary').text()).toContain('32 秒')
  expect(wrapper.find('.execution-spinner').exists()).toBe(false)
  expect(wrapper.attributes('open')).toBeUndefined()
  wrapper.unmount()
})
