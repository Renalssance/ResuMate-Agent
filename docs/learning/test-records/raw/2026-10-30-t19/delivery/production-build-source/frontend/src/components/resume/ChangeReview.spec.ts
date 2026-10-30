import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { TailoringChange } from '../../api/agentRuns'
import ChangeReview from './ChangeReview.vue'
const change: TailoringChange = { id: 'c1', section: '/self_summary', before: '原文', after: '建议', reason: '真实理由', fact_refs: [], requires_input: false, status: 'pending' }
function render(extra: Partial<TailoringChange> = {}) { return mount(ChangeReview, { props: { change: { ...change, ...extra }, decision: { id: 'c1', status: 'pending' }, sources: [] } }) }
function button(wrapper: ReturnType<typeof render>, label: string) { return wrapper.findAll('button').find(item => item.text() === label)! }
describe('change review controls', () => {
 it('offers explicit accept, reject, and undo decisions and a labelled personal edit', async () => {
  const wrapper = render(); await button(wrapper, '接受建议').trigger('click')
  expect(wrapper.emitted('decision')?.[0]).toEqual([{ id: 'c1', status: 'accepted' }])
  await wrapper.setProps({ decision: { id: 'c1', status: 'accepted' } }); await button(wrapper, '撤销决定').trigger('click')
  expect(wrapper.emitted('decision')?.[1]).toEqual([{ id: 'c1', status: 'pending' }])
  await button(wrapper, '拒绝建议').trigger('click'); expect(wrapper.emitted('decision')?.[2]).toEqual([{ id: 'c1', status: 'rejected' }])
  await button(wrapper, '编辑内容').trigger('click'); expect(wrapper.emitted('decision')?.[3]).toEqual([{ id: 'c1', status: 'edited', editedText: '建议' }])
  await wrapper.setProps({ decision: { id: 'c1', status: 'edited', editedText: '建议' } })
  await wrapper.get('textarea').setValue('我的表述'); expect(wrapper.emitted('decision')?.[4]).toEqual([{ id: 'c1', status: 'edited', editedText: '我的表述' }])
  expect(wrapper.get('label').text()).toContain('编辑个人简介'); expect(wrapper.text()).toContain('本人编辑')
  expect(wrapper.get('[data-change-before]').text()).toBe('原文'); expect(wrapper.get('[data-change-after]').text()).toBe('建议')
 })
 it('cannot directly accept a missing fact and identifies personal supplementation', async () => {
  const wrapper = render({ requires_input: true, after: null })
  expect(button(wrapper, '接受建议').attributes('disabled')).toBeDefined()
  await button(wrapper, '编辑内容').trigger('click'); await wrapper.setProps({ decision: { id: 'c1', status: 'edited', editedText: '我的补充' } })
  expect(wrapper.text()).toContain('本人补充'); expect(wrapper.text()).toContain('不会自动写入已确认事实')
 })
 it('freezes controls during save while leaving a confirmed personal edit selectable', async () => {
  const wrapper = render(); await wrapper.setProps({ disabled: true, decision: { id: 'c1', status: 'edited', editedText: '可以复制的本人输入' } })
  expect(wrapper.findAll('button').every(item => item.attributes('disabled') !== undefined)).toBe(true)
  expect(wrapper.get('textarea').attributes('readonly')).toBeDefined()
  await wrapper.setProps({ readonly: true }); expect(wrapper.find('button').exists()).toBe(false); expect(wrapper.get('textarea').element.value).toBe('可以复制的本人输入')
 })
})
