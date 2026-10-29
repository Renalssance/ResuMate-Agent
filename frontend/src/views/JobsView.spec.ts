import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JobsView from './JobsView.vue'
const fixtures = vi.hoisted(() => ({ auth: { token: 'a', isAuthenticated: true }, api: { fetchJobs: vi.fn(), captureJob: vi.fn(), fetchJob: vi.fn(), updateJob: vi.fn(), fetchJobMatches: vi.fn(), parseJob: vi.fn() } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => fixtures.auth }))
vi.mock('../stores/document', () => ({ useDocumentStore: () => ({ parsedResumes: [], loadDocuments: vi.fn() }) }))
vi.mock('../api/jobs', () => fixtures.api)
vi.mock('../services/sse', () => ({ closeTaskProgress: vi.fn(), subscribeTaskProgress: (_id: string, callbacks: any) => callbacks.onMessage({ taskId: 'parse-3', status: 'running', progress: 100, stage: 'llm_analyze', message: '分析中' }) }))
const job = { id: 3, title: '平台工程师', company: '松果科技', status: 'saved', parseStatus: 'pending', text: '开发可靠的业务平台', primaryResumeId: null, primaryResume: null }
const mountView = (progress = false) => mount(JobsView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="typeof to === \'string\' ? to : to.path"><slot /></a>' }, TaskProgress: !progress } } })
beforeEach(() => { fixtures.auth = reactive({ token: 'a', isAuthenticated: true }); vi.resetAllMocks(); fixtures.api.fetchJobs.mockResolvedValue({ items: [], hasMore: false }); fixtures.api.fetchJobMatches.mockResolvedValue({ items: [], hasMore: false }); fixtures.api.fetchJob.mockResolvedValue(job) })
describe('job center', () => {
 it('preserves raw pasted text after capture fails', async () => {
  fixtures.api.captureJob.mockRejectedValue(new Error('收藏失败，请重试')); const w = mountView(); await flushPromises()
  await w.get('input[aria-label="岗位名称"]').setValue('平台工程师'); await w.get('textarea[aria-label="岗位原文"]').setValue('开发可靠的业务平台'); await w.get('form[data-capture]').trigger('submit'); await flushPromises()
  expect(w.text()).toContain('收藏失败'); expect(w.get('textarea').element.value).toBe('开发可靠的业务平台'); w.unmount()
 })
 it('shows a saved job and preserves actual identifiers in workflow links', async () => {
  fixtures.api.fetchJobs.mockResolvedValue({ items: [job], hasMore: false }); const w = mountView(); await flushPromises(); await w.get('button[data-job-id="3"]').trigger('click'); await flushPromises()
  expect(w.get('[aria-label="岗位详情"]').text()).toContain('开发可靠的业务平台'); expect(w.text()).toContain('解析岗位'); expect(w.findAll('a').some(a => a.attributes('href') === '/matching?jdId=3')).toBe(false); w.unmount()
 })
 it('marks a failed parse step as failed and keeps provider details out of the main error message', async () => {
  fixtures.api.fetchJobs.mockResolvedValue({ items: [job], hasMore: false }); fixtures.api.fetchJob.mockResolvedValueOnce(job).mockResolvedValue({ ...job, parseStatus: 'failed' }); fixtures.api.parseJob.mockImplementation(async (_id, accepted) => { accepted('parse-3'); throw new Error('provider error: 503') })
  const w = mountView(true); await flushPromises(); await w.get('[data-job-id="3"]').trigger('click'); await flushPromises(); await w.findAll('button').find(b => b.text() === '解析岗位')!.trigger('click'); await flushPromises()
  expect(w.get('.job-detail .section-head p').text()).toContain('解析失败'); expect(w.find('.parse-step-item.failed').exists()).toBe(true); expect(w.get('.parse-task-title').text()).toBe('解析失败'); expect(w.get('details.parse-error-details').text()).toContain('provider error: 503'); expect(w.findAll('[role="alert"]').some(item => item.text().includes('provider error'))).toBe(false); w.unmount()
 })
 it('resets pagination when status changes', async () => {
  fixtures.api.fetchJobs.mockResolvedValue({ items: [], hasMore: true }); const w = mountView(); await flushPromises(); await w.findAll('button').find(b => b.text() === '下一页')!.trigger('click'); await flushPromises(); await w.get('select[aria-label="岗位状态"]').setValue('archived'); await flushPromises()
  expect(fixtures.api.fetchJobs).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'archived', offset: 0 })); w.unmount()
 })
})
