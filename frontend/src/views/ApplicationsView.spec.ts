import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ApplicationsView from './ApplicationsView.vue'
import { request } from '../services/request'
const records = vi.hoisted(() => ({ calls: [] as { url?: string; method?: string; data: Record<string, unknown> }[] }))
vi.mock('../stores/document', () => ({ useDocumentStore: () => ({ parsedResumes: [{ id: 'resume:1', filename: '已修改的主简历.pdf' }], loadDocuments: vi.fn() }) }))
const version = { id: 'v1', kind: 'resume_version', runId: 'r1', resumeId: 1, jdId: 2, revision: 3, status: 'confirmed', createdAt: '', factRefs: [], structuredContent: { resume: { candidate_name: '张同学', summary: '确认时的简历正文' } } }
const record = { id: 10, company: '示例公司', position: '产品经理', applied_date: '2026-10-30', status: 'applied', resume_id: null, resume_filename: '旧投递简历.pdf', job_url: '', source: '', notes: '', status_events: [], schedules: [], created_at: '', updated_at: '', jd_id: null, resume_version_id: null, submitted_snapshot: null }
const linked = { ...record, resume_id: 1, jd_id: 2, resume_version_id: 'v1', submitted_snapshot: { resumeVersionId: 'v1', revision: 3, jdId: 2, structuredContent: version.structuredContent, factRefs: [], submittedAt: '2026-10-30T12:00:00Z' } }
async function setup(query = '?resumeVersionId=v1&jdId=2') {
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/applications', component: ApplicationsView }, { path: '/resume-versions/:id', component: { template: '<p>简历</p>' } }] })
 await router.push('/applications' + query); await router.isReady()
 const wrapper = mount(ApplicationsView, { global: { plugins: [createPinia(), router] } }); await flushPromises()
 return { wrapper, router }
}
beforeEach(() => {
 records.calls = []
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(version))))
 request.defaults.adapter = async config => {
  records.calls.push({ url: config.url, method: config.method, data: config.data ? JSON.parse(config.data) : {} })
  return { data: config.method === 'get' ? [record] : linked, status: 200, statusText: 'OK', headers: {}, config }
 }
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
it('associates an existing record and renders its immutable snapshot while preserving legacy records', async () => {
 const { wrapper, router } = await setup()
 expect(wrapper.text()).toContain('旧投递简历.pdf')
 expect(wrapper.text()).toContain('关联已确认版本')
 await wrapper.get('select[aria-label="已有投递"]').setValue('10')
 await wrapper.get('.submission-options form').trigger('submit'); await flushPromises()
 expect(records.calls).toContainEqual({ method: 'put', url: '/applications/10/submission', data: { jd_id: 2, resume_version_id: 'v1' } })
 expect(router.currentRoute.value.query).toEqual({})
 expect(wrapper.text()).toContain('已确认版本 · 第 3 版')
 await wrapper.findAll('button').find(button => button.text() === '查看提交时材料')!.trigger('click')
 expect(wrapper.get('[aria-label="提交时材料"]').text()).toContain('确认时的简历正文')
 await wrapper.findAll('button').find(button => button.text() === '编辑')!.trigger('click')
 expect(wrapper.find('.application-edit-form .application-resume select').exists()).toBe(false)
 wrapper.unmount()
})
it('creates a record atomically with the chosen confirmed version and retains the selection after a failed request', async () => {
 const { wrapper } = await setup()
 await wrapper.findAll('button').find(button => button.text() === '新建投递并关联')!.trigger('click')
 expect(wrapper.find('.application-form .application-resume select').exists()).toBe(false)
 await wrapper.get('.application-company input').setValue('新的公司')
 await wrapper.get('.application-position input').setValue('后端开发')
 const originalAdapter = request.defaults.adapter
 request.defaults.adapter = async () => { throw new Error('网络暂时中断') }
 await wrapper.get('.application-form').trigger('submit'); await flushPromises()
 expect(wrapper.text()).toContain('网络暂时中断')
 expect(wrapper.get<HTMLInputElement>('.application-company input').element.value).toBe('新的公司')
 request.defaults.adapter = originalAdapter
 await wrapper.get('.application-form').trigger('submit'); await flushPromises()
 expect(records.calls.find(call => call.method === 'post')?.data).toMatchObject({ company: '新的公司', position: '后端开发', jd_id: 2, resume_version_id: 'v1' })
 expect(wrapper.text()).toContain('已确认版本 · 第 3 版')
 wrapper.unmount()
})

it('defaults a new application to the local calendar day during early morning hours', async () => {
 vi.useFakeTimers({ toFake: ['Date'] })
 vi.setSystemTime(new Date(2026, 9, 30, 1, 0))
 const { wrapper } = await setup('')
 await wrapper.findAll('button').find(button => button.text() === '新增投递')!.trigger('click')
 expect(wrapper.get<HTMLInputElement>('input[type="date"]').element.value).toBe('2026-10-30')
 wrapper.unmount()
})
