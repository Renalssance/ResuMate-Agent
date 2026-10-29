import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useResumeEditorStore } from './resumeEditor'
import type { ResumeVersionArtifact } from '../api/agentRuns'
const auth = vi.hoisted(() => ({ value: null as null | { token: string } }))
vi.mock('./auth', () => ({ useAuthStore: () => auth.value }))

function version(revision = 1): ResumeVersionArtifact {
 return { id: 'v1', runId: 'r1', resumeId: 1, jdId: 2, revision, status: 'draft', reviewable: true, createdAt: '', factRefs: [], sources: [], structuredContent: {
  resume: { candidate_name: '林夏', self_summary: '原始简介', work_experience: [{ company: '小店', description: '原始经历' }], projects: [{ description: '' }] }, inputVersions: { resume: 'v1' }, changes: [
   { id: 'summary', section: '/self_summary', before: '原始简介', after: '建议简介', reason: '突出职责', fact_refs: [], requires_input: false, status: 'pending' },
   { id: 'work', section: '/work_experience/0/description', before: '原始经历', after: '建议经历', reason: '突出经历', fact_refs: [], requires_input: false, status: 'pending' },
   { id: 'missing', section: '/projects/0/description', before: '', after: null, reason: '补充职责', fact_refs: [], requires_input: true, status: 'pending' },
  ],
 } } as ResumeVersionArtifact
}
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }) }
function saved(base: ResumeVersionArtifact, decisions: unknown[], revision = 2) {
 const result = JSON.parse(JSON.stringify(base)) as ResumeVersionArtifact
 result.revision = revision
 result.structuredContent.changes = (result.structuredContent.changes as Record<string, unknown>[]).map((change, i) => ({ ...change, ...(decisions[i] as object) }))
 return result
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }

beforeEach(() => { setActivePinia(createPinia()); auth.value = reactive({ token: 'token' }); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(version()))) })
describe('resume review decisions', () => {
 it('projects accept, reject, edit and undo without mutating original suggestions or sources', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1')
  store.decide({ id: 'summary', status: 'accepted' })
  expect(store.preview.self_summary).toBe('建议简介'); expect(store.dirty).toBe(true)
  store.decide({ id: 'summary', status: 'pending' })
  expect(store.preview.self_summary).toBe('原始简介'); expect(store.dirty).toBe(false)
  store.decide({ id: 'work', status: 'edited', editedText: '我的真实经历' })
  expect(store.preview.work_experience).toEqual([{ company: '小店', description: '我的真实经历' }])
  store.decide({ id: 'work', status: 'rejected' })
  expect(store.preview.work_experience).toEqual([{ company: '小店', description: '原始经历' }])
  expect(store.serverSnapshot?.structuredContent).toEqual(version().structuredContent)
 })
 it('requires an explicit personal edit or rejection for missing information, including clearing a field', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1')
  store.decide({ id: 'missing', status: 'accepted' }); expect(store.localDecisions.missing?.status).toBe('pending')
  store.decide({ id: 'missing', status: 'edited', editedText: '' }); expect(store.localDecisions.missing).toEqual({ id: 'missing', status: 'edited', editedText: '' })
  expect(store.reviewedCount).toBe(1); expect(store.canConfirm).toBe(false)
 })
 it('retains every input on failed save and sends only decisions with the saved revision', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1')
  store.decide({ id: 'summary', status: 'edited', editedText: '保留我的输入' })
  vi.mocked(fetch).mockResolvedValueOnce(response({ message: '保存暂时失败' }, 503))
  await store.save()
  expect(store.error).toContain('保存暂时失败'); expect(store.preview.self_summary).toBe('保留我的输入'); expect(store.dirty).toBe(true)
  const [, options] = vi.mocked(fetch).mock.calls[1]!
  expect(options?.method).toBe('PATCH')
  expect(JSON.parse(String(options?.body))).toEqual({ expectedRevision: 1, changes: [{ id: 'summary', status: 'edited', editedText: '保留我的输入' }, { id: 'work', status: 'pending' }, { id: 'missing', status: 'pending' }] })
 })
 it('locks decisions during a save then adopts the new baseline', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1'); store.decide({ id: 'summary', status: 'accepted' })
  const pending = deferred<Response>(); vi.mocked(fetch).mockReturnValueOnce(pending.promise)
  const request = store.save(); expect(store.editable).toBe(false)
  store.decide({ id: 'summary', status: 'edited', editedText: 'should stay locked' })
  pending.resolve(response(saved(version(), [{ status: 'accepted' }, {}, {}]))); await request
  expect(store.preview.self_summary).toBe('建议简介'); expect(store.dirty).toBe(false); expect(store.serverSnapshot?.revision).toBe(2)
 })
 it('shows the server conflict separately and replays only local changes onto the latest revision', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1'); store.decide({ id: 'summary', status: 'edited', editedText: '本页简介' })
  const latest = saved(version(), [{}, { status: 'edited', editedText: '另一页经历' }, {}])
  vi.mocked(fetch).mockResolvedValueOnce(response({ code: 'revision_conflict' }, 409)).mockResolvedValueOnce(response(latest))
  await store.save()
  expect(store.conflict).toBe(true); expect(store.conflictLatest?.revision).toBe(2); expect(store.preview.self_summary).toBe('本页简介'); expect(store.canSave).toBe(false)
  store.applyLocalChanges()
  expect(store.preview.self_summary).toBe('本页简介'); expect(store.preview.work_experience).toEqual([{ company: '小店', description: '另一页经历' }]); expect(store.serverSnapshot?.revision).toBe(2); expect(store.dirty).toBe(true)
 })
 it('can explicitly discard local decisions in favor of the displayed server version', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1'); store.decide({ id: 'summary', status: 'accepted' })
  vi.mocked(fetch).mockResolvedValueOnce(response({}, 409)).mockResolvedValueOnce(response(saved(version(), [{ status: 'rejected' }, {}, {}])))
  await store.save(); store.useServerVersion()
  expect(store.localDecisions.summary?.status).toBe('rejected'); expect(store.dirty).toBe(false); expect(store.conflict).toBe(false)
 })
 it('retains local copyable input when the other page confirmed and prohibits replay', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1'); store.decide({ id: 'summary', status: 'edited', editedText: '保留便于复制' })
  vi.mocked(fetch).mockResolvedValueOnce(response({}, 409)).mockResolvedValueOnce(response({ ...version(3), status: 'confirmed' }))
  await store.save(); store.applyLocalChanges(); await store.save()
  expect(store.conflictLatest?.status).toBe('confirmed'); expect(store.preview.self_summary).toBe('保留便于复制'); expect(store.editable).toBe(false); expect(store.dirty).toBe(true); expect(fetch).toHaveBeenCalledTimes(3)
 })
 it('confirms only saved reviewed decisions and makes the successful version immutable', async () => {
  const reviewed = saved(version(), [{ status: 'accepted' }, { status: 'rejected' }, { status: 'edited', editedText: '本人补充' }])
  vi.mocked(fetch).mockResolvedValueOnce(response(reviewed))
  const store = useResumeEditorStore(); await store.loadVersion('v1'); expect(store.canConfirm).toBe(true)
  store.decide({ id: 'summary', status: 'rejected' }); expect(store.canConfirm).toBe(false)
  store.decide({ id: 'summary', status: 'accepted' }); expect(store.canConfirm).toBe(true)
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...reviewed, revision: 3, status: 'confirmed' }))
  await store.confirm(); expect(store.editable).toBe(false); expect(store.canConfirm).toBe(false)
  store.decide({ id: 'summary', status: 'pending' }); expect(store.localDecisions.summary?.status).toBe('accepted')
 })
 it('never fills a different version or a signed-out account with a late load response', async () => {
  const first = deferred<Response>(); vi.mocked(fetch).mockReturnValueOnce(first.promise)
  const store = useResumeEditorStore(); const load = store.loadVersion('v1')
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...version(), id: 'v2' })); await store.loadVersion('v2')
  first.resolve(response(version())); await load; expect(store.serverSnapshot?.id).toBe('v2')
  const next = deferred<Response>(); vi.mocked(fetch).mockReturnValueOnce(next.promise); const again = store.loadVersion('v1')
  auth.value!.token = ''; next.resolve(response(version())); await again
  expect(store.serverSnapshot).toBeNull(); expect(store.localDecisions).toEqual({})
 })
 it('ignores a save response after leaving the editor and keeps legacy material read only', async () => {
  const store = useResumeEditorStore(); await store.loadVersion('v1'); store.decide({ id: 'summary', status: 'accepted' })
  const pending = deferred<Response>(); vi.mocked(fetch).mockReturnValueOnce(pending.promise); const save = store.save(); store.clear()
  pending.resolve(response(version(2))); await save; expect(store.serverSnapshot).toBeNull()
  vi.mocked(fetch).mockResolvedValueOnce(response({ ...version(), reviewable: false, structuredContent: { content: '历史文稿' } })); await store.loadVersion('v1')
  expect(store.reviewable).toBe(false); expect(store.editable).toBe(false); expect(store.canConfirm).toBe(false)
 })
})
