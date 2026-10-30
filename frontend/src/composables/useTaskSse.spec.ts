import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { useTaskSse } from './useTaskSse'

afterEach(() => vi.unstubAllGlobals())

it('does not subscribe if acceptance arrives after the task view unmounts', () => {
  const fetch = vi.fn().mockResolvedValue(new Response('data: {"status":"success"}\n\n'))
  vi.stubGlobal('fetch', fetch)
  let task!: ReturnType<typeof useTaskSse>
  const wrapper = mount(defineComponent({ setup() { task = useTaskSse([]); return () => h('div') } }))
  task.startManual('pending-task')
  wrapper.unmount()
  task.start('pending-task')
  expect(fetch).not.toHaveBeenCalled()
})


const parseSteps = [
  { key: 'extract', label: '提取岗位文本' },
  { key: 'llm_analyze', label: '分析岗位要求' },
  { key: 'save', label: '保存结果' },
]

function progressView() {
  let writer!: ReadableStreamDefaultController<Uint8Array>
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream<Uint8Array>({ start(value) { writer = value } }))))
  let task!: ReturnType<typeof useTaskSse>
  const wrapper = mount(defineComponent({ setup() { task = useTaskSse(parseSteps); return () => h('div') } }))
  task.start('accepted-task')
  let seq = 0
  return {
    task, wrapper,
    send(stage: string, status: 'running' | 'failed', progress = 100) {
      writer.enqueue(new TextEncoder().encode(`id: ${++seq}\ndata: ${JSON.stringify({ taskId: 'accepted-task', stage, status, progress, message: stage })}\n\n`))
    },
  }
}

it.each(['failed', 'cancelled'])('ends only the known running step on durable %s projection', async stage => {
  const { task, wrapper, send } = progressView()
  try {
    send('extract', 'running', 30)
    send('llm_analyze', 'running', 100)
    send(stage, 'failed')
    await vi.waitFor(() => expect(task.status.value).toBe('failed'))
    expect(task.steps.value.map(step => step.status)).toEqual(['success', 'failed', 'pending'])
    expect(task.currentStage.value).toBe(stage)
  } finally { wrapper.unmount() }
})

it('keeps API failure terminal when independent progress replays an older running event', async () => {
  const { task, wrapper, send } = progressView()
  try {
    send('llm_analyze', 'running', 90)
    await vi.waitFor(() => expect(task.currentStage.value).toBe('llm_analyze'))
    task.failManual('岗位解析失败')
    send('llm_analyze', 'running', 100)
    await flushPromises()
    expect(task.status.value).toBe('failed')
    expect(task.steps.value.map(step => step.status)).toEqual(['success', 'failed', 'pending'])
    send('failed', 'failed')
    await flushPromises()
    expect(task.steps.value.some(step => step.status === 'running')).toBe(false)
  } finally { wrapper.unmount() }
})

it('does not guess the failed step when only a terminal projection is restored', async () => {
  const { task, wrapper, send } = progressView()
  try {
    send('failed', 'failed')
    await vi.waitFor(() => expect(task.status.value).toBe('failed'))
    expect(task.steps.value.map(step => step.status)).toEqual(['pending', 'pending', 'pending'])
  } finally { wrapper.unmount() }
})
