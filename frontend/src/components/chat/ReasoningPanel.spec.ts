import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ReasoningPanel from './ReasoningPanel.vue'

it('shows streamed reasoning, folds on completion and allows reopening', async () => {
  const wrapper = mount(ReasoningPanel, { props: { content: '正在统计岗位分布', active: true } })
  expect(wrapper.get('details').attributes('open')).toBeDefined()
  expect(wrapper.text()).toContain('正在统计岗位分布')
  await wrapper.setProps({ content: '正在统计岗位分布，接下来分析公司倾向', active: false })
  expect(wrapper.get('details').attributes('open')).toBeUndefined()
  expect(wrapper.text()).toContain('思考过程')
  const details = wrapper.get('details').element as HTMLDetailsElement
  details.open = true
  await wrapper.setProps({ content: '完整思考记录' })
  expect(details.open).toBe(true)
  wrapper.unmount()
})
