import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MarkdownContent from './MarkdownContent.vue'

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'requestAnimationFrame', 'cancelAnimationFrame', 'performance'] }))
afterEach(() => vi.useRealTimers())

it('catches up with a fast burst instead of displaying one character per fixed tick', async () => {
  const w = mount(MarkdownContent, { props: { content: '', streaming: true } })
  await w.setProps({ content: '字'.repeat(240) })
  await vi.advanceTimersByTimeAsync(240)
  expect(w.text().length).toBeGreaterThan(120)
  expect(w.text().length).toBeLessThanOrEqual(240)
  w.unmount()
})

it('follows changing arrival rates and drains the buffer when input pauses', async () => {
  const w = mount(MarkdownContent, { props: { content: '', streaming: true } })
  let content = ''
  for (let i = 0; i < 4; i++) {
    content += '字'.repeat(4)
    await w.setProps({ content })
    await vi.advanceTimersByTimeAsync(100)
  }
  const before = w.text().length
  for (let i = 0; i < 4; i++) {
    content += '字'.repeat(40)
    await w.setProps({ content })
    await vi.advanceTimersByTimeAsync(100)
  }
  expect(w.text().length - before).toBeGreaterThan(100)
  await vi.advanceTimersByTimeAsync(500)
  expect(w.text()).toBe(content)
  expect(w.attributes('aria-busy')).toBe('false')
  w.unmount()
})

it('finishes immediately and renders historical/replaced text without a typing delay', async () => {
  const w = mount(MarkdownContent, { props: { content: '', streaming: true } })
  await w.setProps({ content: '未显示内容'.repeat(100) })
  await w.setProps({ streaming: false })
  expect(w.text()).toBe('未显示内容'.repeat(100))
  expect(w.attributes('aria-busy')).toBe('false')
  await w.setProps({ content: '历史消息' })
  expect(w.text()).toBe('历史消息')
  await w.setProps({ content: '新的消息😀', streaming: true })
  expect(w.text()).toBe('新的消息😀')
  w.unmount()
  expect(vi.getTimerCount()).toBe(0)
})
