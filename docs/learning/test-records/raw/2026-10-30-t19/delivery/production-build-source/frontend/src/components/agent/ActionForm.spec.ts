import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ActionForm from './ActionForm.vue'
const action = { actionId: 'a1', kind: 'input' as const, payload: { question: '你负责什么工作？' }, revision: 1 }
describe('applicant question', () => {
 it('labels the answer with the actual question and submits from the keyboard form', async () => { const wrapper = mount(ActionForm, { props: { action, modelValue: '负责 API', busy: false, error: '' } }); expect(wrapper.get('label').text()).toBe('你负责什么工作？'); expect(wrapper.get('label').attributes('for')).toBe(wrapper.get('textarea').attributes('id')); await wrapper.get('form').trigger('submit'); expect(wrapper.emitted('submit')?.length).toBe(1) })
 it('associates errors and retains the supplied answer', () => { const wrapper = mount(ActionForm, { props: { action, modelValue: '我的回答', busy: false, error: '状态已变化' } }); expect(wrapper.get('textarea').element.value).toBe('我的回答'); expect(wrapper.get('textarea').attributes('aria-describedby')).toBe(wrapper.get('[role="alert"]').attributes('id')) })
})
