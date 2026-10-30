import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ArtifactCard from './ArtifactCard.vue'
import RunTimeline from './RunTimeline.vue'
describe('task material display', () => {
 it('renders structured material as text and names the draft without internal identifiers', () => {
  const wrapper = mount(ArtifactCard, { global: { stubs: { RouterLink: RouterLinkStub } }, props: { artifact: { id: 'private-id', runId: 'private-run', resumeId: 1, jdId: 2, revision: 1, status: 'draft', structuredContent: { summary: '<img src=x onerror=alert(1)>', experience: ['负责 API 设计'], work_experience: [{ company: '示例团队', description: '设计 API' }] }, factRefs: [], createdAt: '' } } })
  expect(wrapper.text()).toContain('个人简介'); expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>'); expect(wrapper.find('img').exists()).toBe(false); expect(wrapper.text()).not.toContain('private-id'); expect(wrapper.text()).toContain('公司'); expect(wrapper.text()).toContain('经历说明'); expect(wrapper.text()).not.toContain('company')
 })
 it('shows task phases and translated tool progress without broadcasting model text', () => {
  const events = [ { runId: 'r', seq: 1, createdAt: '', type: 'tool.started', payload: { tool_name: 'get_application_context', operation_key: 'call-uuid' } }, { runId: 'r', seq: 2, createdAt: '', type: 'assistant.delta', payload: { text: 'model-token' } } ]
  const wrapper = mount(RunTimeline, { props: { events, status: 'running' } })
  expect(wrapper.text()).toContain('读取岗位和简历'); expect(wrapper.text()).not.toContain('get_application_context'); expect(wrapper.text()).not.toContain('model-token'); expect(wrapper.text()).not.toContain('call-uuid')
 })
})

it('does not show an interrupted tool as still processing after task cancellation', () => {
 const wrapper = mount(RunTimeline, { props: { status: 'cancelled', events: [{ runId: 'r', seq: 1, createdAt: '', type: 'tool.started', payload: { tool_name: 'ask_applicant', operation_key: 'call' } }] } })
 expect(wrapper.text()).toContain('已停止'); expect(wrapper.text()).not.toContain('处理中')
})

it('names export progress as PDF generation instead of resume preparation', () => {
 const wrapper = mount(RunTimeline, { props: { kind: 'resume_export', status: 'succeeded', events: [
  { runId: 'r', seq: 1, createdAt: '', type: 'run.status', payload: { status: 'running' } },
  { runId: 'r', seq: 2, createdAt: '', type: 'run.status', payload: { status: 'succeeded' } },
 ] } })
 expect(wrapper.text()).toContain('正在导出 PDF'); expect(wrapper.text()).toContain('PDF 已导出')
})
