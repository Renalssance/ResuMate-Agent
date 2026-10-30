import { test, expect, createRun, snapshot, waitForRun } from './support/fixtures'
import type { Page } from '@playwright/test'
import { writeFileSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'

const question = '你负责什么工作？'
const longAnswer = '负责 API 和数据库设计。' + '与团队核对接口需求、维护数据结构，并以实际项目职责为依据整理待审阅材料。'.repeat(10)
interface Metrics {
  inputSamples: number[]; recordInputs: boolean; onlineAt: number | null
  completedAt: number | null; completedWallTime: number | null
}
async function instrument(page: Page) {
  const pageErrors: string[] = [], cspViolations: unknown[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.exposeFunction('recordProductionCsp', (violation: unknown) => cspViolations.push(violation))
  await page.addInitScript(() => {
    const target = window as unknown as { __t17: Metrics; recordProductionCsp: (value: unknown) => void }
    const state = target.__t17 = { inputSamples: [], recordInputs: false, onlineAt: null, completedAt: null, completedWallTime: null }
    document.addEventListener('securitypolicyviolation', event => target.recordProductionCsp({
      directive: event.violatedDirective, blockedURI: event.blockedURI, disposition: event.disposition,
    }))
    document.addEventListener('input', event => {
      if (!state.recordInputs || !(event.target instanceof HTMLTextAreaElement)) return
      const started = performance.now()
      requestAnimationFrame(() => state.inputSamples.push(performance.now() - started))
    }, true)
    window.addEventListener('online', () => { state.onlineAt = performance.now() })
    new MutationObserver(() => {
      if (state.completedAt === null && [...document.querySelectorAll('h2')].some(item => item.textContent === '材料已生成')) {
        state.completedAt = performance.now(); state.completedWallTime = Date.now()
      }
    }).observe(document, { childList: true, subtree: true, characterData: true })
  })
  return { pageErrors, cspViolations }
}
async function metrics(page: Page): Promise<Metrics> {
  return page.evaluate(() => (window as unknown as { __t17: Metrics }).__t17)
}
function save(name: string, data: unknown) {
  writeFileSync(test.info().outputPath(name), JSON.stringify(data, null, 2))
}
async function capture(page: Page, name: string, width: number) {
  await page.setViewportSize({ width, height: width < 700 ? 844 : 1100 })
  if (width < 700) {
    const menu = page.getByRole('button', { name: '打开导航', exact: true })
    if (await menu.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  await page.screenshot({ path: test.info().outputPath(`${name}-${width}.png`), fullPage: true, animations: 'disabled' })
}
async function viewChunks(page: Page) {
  return page.evaluate(() => performance.getEntriesByType('resource').map(item => new URL(item.name).pathname).filter(name => /View-[^/]+\.js$/.test(name)))
}
function terminalEvent(runId: string) {
  return JSON.parse(execFileSync('.venv/bin/python', ['-c', [
    'import sqlite3, json, sys',
    'db=sqlite3.connect(sys.argv[1]); db.row_factory=sqlite3.Row',
    "rows=[dict(row) for row in db.execute('SELECT seq,type,created_at,payload FROM agent_run_events WHERE run_id=? ORDER BY seq',(sys.argv[2],))]",
    'print(json.dumps(rows))',
  ].join('\n'), join(process.env.RESUMATE_E2E_ROOT!, 'resumate.db'), runId], { encoding: 'utf8' })) as Array<{ seq: number; type: string; created_at: string; payload: string }>
}

test('production lazy routes, local input frames, long layouts, upload and PDF under CSP', async ({ page, api }) => {
  const security = await instrument(page)
  const runId = await createRun(api)
  const mainResponse = await page.goto(`/agent/tasks/${runId}`)
  const csp = mainResponse!.headers()['content-security-policy']
  expect(csp).toContain("script-src 'self'"); expect(csp).not.toContain('unsafe-eval')
  expect(mainResponse!.headers()['server']).toContain('nginx')
  await expect(page.getByLabel(question, { exact: true })).toBeVisible()
  const initialChunks = await viewChunks(page)
  expect(initialChunks.some(path => path.includes('/AgentTaskView-'))).toBe(true)
  expect(initialChunks.some(path => /\/(Jobs|Applications|Interview)View-/.test(path))).toBe(false)

  const input = page.getByLabel(question, { exact: true })
  await page.evaluate(() => { (window as unknown as { __t17: Metrics }).__t17.recordInputs = true })
  await input.pressSequentially('performance-input-20', { delay: 25 })
  await expect.poll(async () => (await metrics(page)).inputSamples.length).toBe(20)
  await page.evaluate(() => { (window as unknown as { __t17: Metrics }).__t17.recordInputs = false })
  const samples = (await metrics(page)).inputSamples
  const sorted = [...samples].sort((a, b) => a - b)
  const inputEvidence = { samples_ms: samples, p95_ms: sorted[Math.ceil(samples.length * .95) - 1], max_ms: Math.max(...samples), measurement: 'browser input capture listener to requestAnimationFrame; excludes Playwright RTT', domElements: await page.locator('*').count() }
  save('input-latency.json', inputEvidence)
  expect(inputEvidence.max_ms).toBeLessThanOrEqual(100)
  await input.fill(longAnswer)
  for (const width of [1440, 390, 320]) await capture(page, 'waiting-long-answer', width)
  await input.fill(''); await page.getByRole('button', { name: '继续任务', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('请填写补充信息')
  await capture(page, 'answer-validation-error', 320)
  await input.fill(longAnswer); await page.getByRole('button', { name: '继续任务', exact: true }).click()
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  const done = await waitForRun(api, runId, 'succeeded')
  const completed = await metrics(page), events = terminalEvent(runId)
  const final = events.at(-1)!
  const eventToUi = completed.completedWallTime! - Date.parse(final.created_at.replace(' ', 'T') + 'Z')
  save('normal-run.json', { runId, event_count: events.length, events, completed, event_created_to_ui_ms: eventToUi, measurement: 'one real SQL event created_at to browser DOM visibility sample; includes commit, not a P95 load claim' })
  expect(eventToUi).toBeLessThanOrEqual(1000)
  for (const width of [1440, 390, 320]) await capture(page, 'completed-long-material', width)

  const versionId = done.outputRefs[0]!.id
  const version = await (await api.get(`/api/resume-versions/${versionId}`)).json()
  expect((await api.patch(`/api/resume-versions/${versionId}`, { data: { expectedRevision: 1,
    changes: version.structuredContent.changes.map((item: { id: string; requires_input: boolean }) => ({ id: item.id, status: item.requires_input ? 'rejected' : 'accepted' })),
  } })).status()).toBe(200)
  expect((await api.post(`/api/resume-versions/${versionId}/confirm`, { data: { expectedRevision: 2 } })).status()).toBe(200)
  await page.goto(`/resume-versions/${versionId}`)
  const accepted = page.waitForResponse(response => response.url().endsWith(`/api/resume-versions/${versionId}/export`))
  await page.getByRole('button', { name: '导出 PDF', exact: true }).click()
  expect((await accepted).status()).toBe(202)
  await expect(page.getByRole('button', { name: '下载 PDF', exact: true })).toBeVisible()
  const pendingDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 PDF', exact: true }).click()
  const pdfPath = test.info().outputPath('production-resume.pdf')
  await (await pendingDownload).saveAs(pdfPath)
  expect(readFileSync(pdfPath).subarray(0, 5).toString()).toBe('%PDF-')

  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.getByRole('link', { name: '岗位中心', exact: true }).click()
  await expect(page).toHaveURL('/jobs')
  const afterJobsChunks = await viewChunks(page)
  expect(afterJobsChunks.some(path => path.includes('/JobsView-'))).toBe(true)
  await page.getByRole('link', { name: '文档管理', exact: true }).click()
  const upload = page.waitForResponse(response => response.url().endsWith('/api/documents') && response.request().method() === 'POST')
  await page.getByLabel('上传简历文件').setInputFiles({ name: '生产代理上传验证.txt', mimeType: 'text/plain', buffer: Buffer.from('工作经历\n示例团队 API开发 2022-2025\n负责 API 和数据库设计，与团队核对接口需求。') })
  const uploadResponse = await upload
  expect(uploadResponse.status()).toBe(202)
  const uploadId = (await uploadResponse.json()).taskId
  await expect.poll(async () => ['succeeded', 'failed', 'cancelled'].includes((await snapshot(api, uploadId)).status)).toBe(true)
  const uploadSnapshot = await snapshot(api, uploadId)
  save('upload-result.json', { snapshot: uploadSnapshot, events: terminalEvent(uploadId) })
  expect(uploadSnapshot.status).toBe('succeeded')
  await page.goto('/')
  await expect(page.getByRole('link', { name: '登录', exact: true }).or(page.getByRole('link', { name: '进入工作台', exact: true })).first()).toBeVisible()
  save('production-security-and-routes.json', { csp, initialChunks, afterJobsChunks, uploadId, pdfBytes: readFileSync(pdfPath).length, ...security })
  expect(security.pageErrors).toEqual([]); expect(security.cspViolations).toEqual([])
})

test('online wakes maximum backoff and displays the worker result within five seconds', async ({ page, context, api }) => {
  const security = await instrument(page)
  const runId = await createRun(api)
  const streamRequests: Array<{ url: string; at: number }> = []
  const failedRequests: Array<{ at: number; error: string | null }> = []
  page.on('request', request => { if (request.url().includes(`/runs/${runId}/events?`)) streamRequests.push({ url: request.url(), at: Date.now() }) })
  page.on('requestfailed', request => { if (request.url().includes(`/runs/${runId}`)) failedRequests.push({ at: Date.now(), error: request.failure()?.errorText ?? null }) })
  await page.goto(`/agent/tasks/${runId}`)
  await expect(page.getByLabel(question, { exact: true })).toBeVisible()
  await page.getByLabel(question, { exact: true }).fill('断网时保留的未提交回答')
  const before = await snapshot(api, runId)
  const offlineAt = Date.now()
  await context.setOffline(true)
  await expect(page.getByText(/网络连接已断开/)).toBeVisible()
  const response = await api.post(`/api/agent/runs/${runId}/actions/${before.actions[0]!.actionId}`, { data: { decision: 'submit', answers: { answer: longAnswer }, expectedRevision: before.actions[0]!.revision } })
  expect(response.status()).toBe(202)
  await waitForRun(api, runId, 'succeeded')
  await page.waitForTimeout(Math.max(0, 35_000 - (Date.now() - offlineAt)))
  await expect(page.getByLabel(question, { exact: true })).toHaveValue('断网时保留的未提交回答')
  await capture(page, 'offline-max-backoff', 390)
  const offlineDuration = Date.now() - offlineAt
  const onlineWallTime = Date.now()
  await context.setOffline(false)
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible({ timeout: 5000 })
  await expect(page.getByText(/网络连接已断开/)).toHaveCount(0)
  const result = await metrics(page)
  const recoveryMs = result.completedAt! - result.onlineAt!
  // Remain connected past the former 15 s timer to catch a duplicate reconnect.
  await page.waitForTimeout(15_100)
  const resumed = streamRequests.filter(item => item.at >= onlineWallTime)
  const evidence = { runId, offline_ms: offlineDuration, recovery_ms: recoveryMs, browser_clock: result, streamRequests, failedRequests, ...security }
  save('offline-recovery.json', evidence)
  expect(offlineDuration).toBeGreaterThanOrEqual(35_000)
  expect(result.onlineAt).not.toBeNull(); expect(recoveryMs).toBeGreaterThanOrEqual(0); expect(recoveryMs).toBeLessThanOrEqual(5000)
  expect(resumed).toHaveLength(1)
  expect(security.pageErrors).toEqual([]); expect(security.cspViolations).toEqual([])
  await capture(page, 'online-latest-result', 1440)
})
