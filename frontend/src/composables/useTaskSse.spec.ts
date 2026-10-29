import { mount } from '@vue/test-utils'
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
