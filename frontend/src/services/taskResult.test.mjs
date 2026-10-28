import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'

class FakeEventSource {
  static instances = []
  closed = false
  onmessage = null
  onerror = null
  constructor(url) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  close() { this.closed = true }
  emit(event) { this.onmessage?.({ data: JSON.stringify(event) }) }
}
globalThis.EventSource = FakeEventSource
const tempDir = await mkdtemp(join(new URL('../..', import.meta.url).pathname, '.task-result-test-'))
try {
  const entry = join(tempDir, 'entry.ts')
  const bundle = join(tempDir, 'entry.cjs')
  await writeFile(entry, `
    export { createDocumentUploadQueue } from ${JSON.stringify(new URL('../composables/useDocumentParseTasks.ts', import.meta.url).pathname)}
    export { request } from ${JSON.stringify(new URL('./request.ts', import.meta.url).pathname)}
    export { subscribeTaskProgress } from ${JSON.stringify(new URL('./sse.ts', import.meta.url).pathname)}
    export { uploadDocumentsApi, reparseDocumentApi } from ${JSON.stringify(new URL('../api/documents.ts', import.meta.url).pathname)}
    export { createRunApi, generateCandidateQuestionsApi } from ${JSON.stringify(new URL('../api/runs.ts', import.meta.url).pathname)}
  `)
  await build({ entryPoints: [entry], bundle: true, format: 'cjs', platform: 'node', outfile: bundle, logLevel: 'silent' })
  const api = await import(pathToFileURL(bundle))
  let taskId = ''
  const requestedUrls = []
  api.request.defaults.adapter = async config => {
    assert.equal(config.headers.get('Prefer'), 'respond-async')
    requestedUrls.push(config.url)
    return { data: { taskId }, status: 202, statusText: 'Accepted', headers: {}, config }
  }
  const document = {
    id: 'resume:1', type: 'resume', filename: 'resume.txt', size: 42,
    raw_text: 'Candidate text', parsed_content: {}, vectorized: true, local_stored: true,
    parse_status: 'success', created_at: '2026-10-17T00:00:00Z',
  }
  const run = { run_id: 7, job_title: 'Backend', candidates: [], taskId: 'run-task' }
  const report = {
    run_id: 7, candidate_id: 8, candidate_name: 'Candidate', filename: 'resume.txt',
    resume_profile: { candidate_name: 'Candidate', contact: {}, education: [], work_experience: [], projects: [], skills: [], achievements: [], ambiguities: [], source_refs: [] },
    evaluations: [], total_score: 60, recommendation: 'hold', top_strengths: [],
    summary: 'Assessment', formal_questions: [], ambiguity_followups: [],
  }
  const form = new FormData()
  form.append('files', new Blob(['Candidate text']), 'resume.txt')
  const cases = [
    ['upload-task', () => api.uploadDocumentsApi(form), { documents: [document] }, { documents: [document], taskId: 'upload-task' }],
    ['reparse-task', () => api.reparseDocumentApi('resume:1', 'reparse-task'), { document }, document],
    ['run-task', () => api.createRunApi({ jd_document_id: 'jd:1', resume_document_ids: ['resume:1'], taskId: 'run-task' }), run, run],
    ['questions-task', () => api.generateCandidateQuestionsApi(7, 8, 'questions-task', 3), report, report],
  ]
  for (const [id, submit, data, expected] of cases) {
    taskId = id
    const ui = api.subscribeTaskProgress(id, { onMessage() {} })
    const uiSource = FakeEventSource.instances.at(-1)
    let settled = false
    const result = submit()
    result.then(() => { settled = true }, () => { settled = true })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(settled, false, 'HTTP 202 must not finish the caller or release its upload queue slot')
    assert.equal(uiSource.closed, false, 'waiting for results must preserve the existing progress subscription')
    const waiter = FakeEventSource.instances.at(-1)
    assert.notEqual(waiter, uiSource, 'result and UI subscriptions own separate connections')
    assert.equal(waiter.url, `/api/tasks/${id}/events`)
    waiter.emit({ taskId: id, stage: 'llm_analyze', status: 'running', progress: 45, message: 'Working', data: {} })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(settled, false)
    waiter.emit({ taskId: id, stage: 'completed', status: 'success', progress: 100, message: 'Done', data })
    assert.deepEqual(await result, expected, `${id} must retain the synchronous API result shape`)
    assert.equal(waiter.closed, true)
    assert.equal(uiSource.closed, false)
    ui.close()
  }
  assert.deepEqual(requestedUrls, [
    '/documents', '/documents/resume:1/parse?task_id=reparse-task', '/runs',
    '/runs/7/candidates/8/questions?question_count=3&task_id=questions-task',
  ])
  taskId = 'failed-task'
  const failed = api.createRunApi({ jd_document_id: 'jd:1', resume_document_ids: ['resume:1'] })
  await new Promise(resolve => setImmediate(resolve))
  const source = FakeEventSource.instances.at(-1)
  source.emit({ taskId, stage: 'failed', status: 'failed', progress: 100, message: 'Model request failed', data: {} })
  await assert.rejects(failed, /Model request failed/)
  assert.equal(source.closed, true)

  taskId = 'disconnected-task'
  const disconnected = api.createRunApi({ jd_document_id: 'jd:1', resume_document_ids: ['resume:1'] })
  await new Promise(resolve => setImmediate(resolve))
  const disconnectedSource = FakeEventSource.instances.at(-1)
  disconnectedSource.onerror()
  await assert.rejects(disconnected, /connection/i)
  assert.equal(disconnectedSource.closed, true)
  // A failed queued resume must not determine a later text upload's outcome.
  let finishFirst
  const firstUpload = new Promise(resolve => { finishFirst = resolve })
  let queueId = 0
  const queue = api.createDocumentUploadQueue({
    createTaskId: () => `queue-${++queueId}`,
    subscribe: () => ({ close() {} }),
    upload: async (_type, file) => {
      if (file.name === 'first.pdf') await firstUpload
      if (file.name === 'bad.pdf') throw new Error('Resume failed')
      return { documents: [document] }
    },
  })
  const resumes = queue.enqueueFiles('resume', [new File(['one'], 'first.pdf'), new File(['bad'], 'bad.pdf')])
  const textUpload = queue.enqueueFiles('jd', [new File(['text'], 'jd.txt')])
  finishFirst()
  assert.deepEqual(await resumes, [true, false], 'each file must expose its own queue outcome')
  assert.deepEqual(await textUpload, [true], 'successful text must remain successful after another queued upload fails')
  console.log('Async API mappings, independent subscriptions, pending waits, and failures passed.')
} finally {
  await rm(tempDir, { recursive: true, force: true })
}
