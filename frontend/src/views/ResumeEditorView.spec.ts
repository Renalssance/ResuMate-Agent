import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ResumeEditorView from './ResumeEditorView.vue'
import { useResumeEditorStore } from '../stores/resumeEditor'
const auth = vi.hoisted(() => ({ value: null as null | { token: string; isAuthenticated: boolean } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => auth.value }))
const artifact = { id: 'v1', runId: 'r1', resumeId: 1, jdId: 2, revision: 1, status: 'draft', reviewable: true, createdAt: '', factRefs: [], sources: [], structuredContent: { resume: { self_summary: '原文' }, inputVersions: {}, changes: [{ id: 'c1', section: '/self_summary', before: '原文', after: '建议', reason: '突出职责', fact_refs: [], requires_input: false, status: 'pending' }] } }
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
async function setup() {
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/resume-versions/:versionId', component: ResumeEditorView }, { path: '/agent/tasks/:runId?', component: { template: '<p>材料准备</p>' } }, { path: '/applications', component: { template: '<p>投递记录</p>' } }] })
 await router.push('/resume-versions/v1'); await router.isReady()
 const pinia = createPinia(); const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [pinia, router] } }); await flushPromises()
 return { router, wrapper, store: useResumeEditorStore(pinia) }
}
beforeEach(() => { auth.value = reactive({ token: 'token', isAuthenticated: true }); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(artifact))) })
afterEach(() => vi.restoreAllMocks())
describe('resume editor page', () => {
 it('protects unsaved input on route leave and browser close, and allows leaving after a successful save', async () => {
  const { wrapper, store, router } = await setup()
  await wrapper.findAll('button').find(button => button.text() === '编辑内容')!.trigger('click')
  await wrapper.get('textarea').setValue('保留本页输入'); expect(store.preview.self_summary).toBe('保留本页输入')
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  await router.push('/agent/tasks/r1'); expect(router.currentRoute.value.path).toBe('/resume-versions/v1'); expect(wrapper.get('textarea').element.value).toBe('保留本页输入')
  const close = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(close); expect(close.defaultPrevented).toBe(true)
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...artifact, revision: 2, structuredContent: { ...artifact.structuredContent, changes: [{ ...artifact.structuredContent.changes[0], status: 'edited', editedText: '保留本页输入' }] } }))
  await wrapper.findAll('button').find(button => button.text() === '保存草稿')!.trigger('click'); await flushPromises()
  expect(store.dirty).toBe(false); await router.push('/agent/tasks/r1'); expect(router.currentRoute.value.path).toBe('/agent/tasks/r1'); expect(confirm).toHaveBeenCalledTimes(1)
  wrapper.unmount()
 })
 it('renders a retryable loading failure and does not expose actions for confirmed or legacy material', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(response({ message: '找不到这个版本' }, 404))
  const { wrapper, store } = await setup()
  expect(wrapper.get('[role="alert"]').text()).toContain('找不到这个版本'); expect(wrapper.text()).toContain('重新加载')
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...artifact, status: 'confirmed' })); await store.loadVersion('v1'); await flushPromises()
  expect(wrapper.text()).toContain('版本已确认'); expect(wrapper.find('textarea').exists()).toBe(false); expect(wrapper.findAll('button').some(button => button.text() === '接受建议')).toBe(false)
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...artifact, reviewable: false, structuredContent: { content: '历史材料原文' } })); await store.loadVersion('v1'); await flushPromises()
  expect(wrapper.text()).toContain('重新准备材料'); expect(wrapper.text()).toContain('历史材料原文'); expect(wrapper.findAll('button').some(button => button.text() === '保存草稿')).toBe(false)
  wrapper.unmount()
 })
})

it('exports the confirmed version with an idempotency key and navigates to its task, while association preserves the version and job', async () => {
 vi.mocked(fetch).mockResolvedValueOnce(response({ ...artifact, status: 'confirmed' }))
 const { wrapper, router } = await setup()
 const association = wrapper.findAll('a').find(link => link.text() === '关联投递')
 expect(association?.attributes('href')).toBe('/applications?resumeVersionId=v1&jdId=2')
 const exportButton = wrapper.findAll('button').find(button => button.text() === '导出 PDF')
 expect(exportButton).toBeDefined()
 vi.mocked(fetch).mockResolvedValueOnce(response({ runId: 'pdf-run', status: 'queued' }, 202))
 await exportButton!.trigger('click'); await flushPromises()
 expect(fetch).toHaveBeenLastCalledWith('/api/resume-versions/v1/export', expect.objectContaining({ method: 'POST', body: expect.stringMatching(/"requestId":"[^" ]+"/) }))
 expect(router.currentRoute.value.path).toBe('/agent/tasks/pdf-run')
 wrapper.unmount()
})
