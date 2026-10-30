import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProfileFacts from './ProfileFacts.vue'
const fixtures = vi.hoisted(() => ({ auth: { token: 'a' }, api: { fetchProfileFacts: vi.fn(), createProfileFact: vi.fn(), updateProfileFact: vi.fn(), deleteProfileFact: vi.fn(), fetchFactHistory: vi.fn() } }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => fixtures.auth }))
vi.mock('../api/profileFacts', () => fixtures.api)
const fact = { id: 'v1', factKey: 'f', kind: 'experience', content: { text: '负责平台服务' }, sourceDocumentId: 1, revision: 1, confirmedAt: null, deletedAt: null }
beforeEach(() => { fixtures.auth = reactive({ token: 'a' }); vi.resetAllMocks(); fixtures.api.fetchProfileFacts.mockResolvedValue({ items: [] }); fixtures.api.createProfileFact.mockResolvedValue(fact) })
const byText = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(b => b.text() === text)!
describe('confirmed profile facts', () => {
 it('saves selected parsed experience unconfirmed unless the user explicitly confirms it', async () => {
  const w = mount(ProfileFacts, { props: { resumeId: 'resume:1', parsedContent: { work_experience: [{ company: '松果科技', title: '工程师', description: '负责平台服务' }] } } }); await flushPromises()
  await w.get('select[aria-label="从简历选择经历"]').setValue('work_experience:0'); expect(w.get('textarea').element.value).toContain('负责平台服务')
  expect((w.get('input[type="checkbox"][data-confirm]').element as HTMLInputElement).checked).toBe(false)
  await w.get('form').trigger('submit'); await flushPromises(); expect(fixtures.api.createProfileFact).toHaveBeenCalledWith(expect.objectContaining({ confirmed: false, sourceDocumentId: 1 })); await w.get('select[aria-label="从简历选择经历"]').setValue('work_experience:0')
  await w.get('input[data-confirm]').setValue(true); await w.get('form').trigger('submit'); await flushPromises()
  expect(fixtures.api.createProfileFact).toHaveBeenCalledWith(expect.objectContaining({ confirmed: true, sourceDocumentId: 1, content: expect.objectContaining({ text: expect.stringContaining('负责平台服务') }) })); w.unmount()
 })
 it('keeps edited text on version conflict and offers current data reload', async () => {
  fixtures.api.fetchProfileFacts.mockResolvedValue({ items: [fact] }); fixtures.api.updateProfileFact.mockRejectedValue(Object.assign(new Error('changed'), { status: 409 }))
  const w = mount(ProfileFacts, { props: { resumeId: 'resume:1' } }); await flushPromises(); await byText(w, '编辑事实').trigger('click'); await w.get('textarea').setValue('新增真实职责'); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('textarea').element.value).toBe('新增真实职责'); expect(w.text()).toContain('已在其他页面更新'); expect(byText(w, '重新加载事实')).toBeTruthy(); w.unmount()
 })
 it('does not display facts from an older resume request after switching', async () => {
  let resolveOld!: (value: unknown) => void; fixtures.api.fetchProfileFacts.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockResolvedValue({ items: [] })
  const w = mount(ProfileFacts, { props: { resumeId: 'resume:1' } }); await w.setProps({ resumeId: 'resume:2' }); await flushPromises(); resolveOld({ items: [fact] }); await flushPromises(); expect(w.text()).not.toContain('负责平台服务'); w.unmount()
 })
})
