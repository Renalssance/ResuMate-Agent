import { test, expect, waitForRun } from './support/fixtures'
import type { Page, APIRequestContext } from '@playwright/test'
import { existsSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'

const state = () => process.env.RESUMATE_E2E_ROOT!
const pauseFile = () => join(state(), 'legacy-pause')
function pauseModel() { rmSync(join(state(), 'legacy-model-started'), { force: true }); writeFileSync(pauseFile(), '') }
function resumeModel() { rmSync(pauseFile(), { force: true }) }
async function modelStarted() { await expect.poll(() => existsSync(join(state(), 'legacy-model-started'))).toBe(true) }
const resumeText = '工作经历\n示例团队 | API开发 | 2022-2025\n负责 API 和数据库设计，与团队核对接口需求和联调结果。\n项目经历\n接口服务项目，参与接口设计、日志排查和测试验证。'
const longFilename = '示例求职者_接口开发与数据库设计_跨团队联调和故障排查经历_用于检查手机布局的较长简历文件名.txt'

async function capture(page: Page, name: string, mobile = false) {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1100 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)
}
async function taskSnapshot(api: APIRequestContext, taskId: string) { return (await api.get(`/api/agent/runs/${taskId}`)).json() }
async function savedJob(api: APIRequestContext, marker = '') {
  const captureId = randomUUID().slice(0, 6)
  const response = await api.post('/api/jobs', { data: { title: `恢复验收 API 工程师 ${captureId}`, text: `负责 API 和数据库设计，需要真实接口开发经历。测试岗位 ${captureId}。${marker}` } })
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()).job.id as number
}
async function upload(api: APIRequestContext, text: string, filename = longFilename) {
  const response = await api.post('/api/documents', { headers: { Prefer: 'respond-async' }, multipart: { document_type: 'resume', task_id: randomUUID(), files: { name: filename, mimeType: 'text/plain', buffer: Buffer.from(text) } } })
  expect(response.status(), await response.text()).toBe(202)
  return (await response.json()).taskId as string
}

test.afterEach(() => resumeModel())

test('上传、匹配和出题离开重开后读取同一持久任务及结果', async ({ page, api }) => {
  test.setTimeout(120_000)
  await page.goto('/documents')
  pauseModel()
  const acceptedUpload = page.waitForResponse(r => r.url().endsWith('/api/documents') && r.request().method() === 'POST')
  await page.getByLabel('上传简历文件').setInputFiles({ name: longFilename, mimeType: 'text/plain', buffer: Buffer.from(resumeText) })
  const uploadResponse = await acceptedUpload
  expect(uploadResponse.status()).toBe(202)
  const uploadId = (await uploadResponse.json()).taskId
  await modelStarted()
  await expect(page.locator(`a[href="/agent/tasks/${uploadId}"]`)).toBeVisible()
  await capture(page, 'document-pending-long-desktop')
  await capture(page, 'document-pending-long-mobile', true)
  await page.goto('/agent/tasks')
  await page.goto('/documents')
  await expect(page.locator(`a[href="/agent/tasks/${uploadId}"]`)).toBeVisible()
  await capture(page, 'document-reopened-mobile', true)
  resumeModel()
  await waitForRun(api, uploadId, 'succeeded')
  const document = (await taskSnapshot(api, uploadId)).result.documents[0]
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  const row = page.getByRole('row').filter({ has: page.getByRole('button', { name: longFilename, exact: true }) })
  pauseModel()
  const acceptedReparse = page.waitForResponse(r => r.url().includes('/parse?task_id=') && r.request().method() === 'POST')
  await row.getByRole('button', { name: '重解析', exact: true }).click()
  const reparseId = (await (await acceptedReparse).json()).taskId
  await modelStarted()
  await page.reload()
  await expect(page.locator(`a[href="/agent/tasks/${reparseId}"]`)).toBeVisible()
  await capture(page, 'document-reparse-reopened-mobile', true)
  resumeModel()
  await waitForRun(api, reparseId, 'succeeded')
  expect((await taskSnapshot(api, reparseId)).result.id).toBe(document.id)
  const jobId = await savedJob(api)
  const parseResponse = await api.post(`/api/jobs/${jobId}/parse`)
  expect(parseResponse.status()).toBe(202)
  await waitForRun(api, (await parseResponse.json()).taskId, 'succeeded')

  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto(`/matching?jdId=${jobId}&resumeId=${document.id.split(':')[1]}`)
  await expect(page.getByRole('button', { name: '开始匹配', exact: true })).toBeEnabled()
  pauseModel()
  const acceptedMatch = page.waitForResponse(r => r.url().endsWith('/api/runs') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '开始匹配', exact: true }).click()
  const matchId = (await (await acceptedMatch).json()).taskId
  await modelStarted()
  await page.goto('/documents'); await page.goto('/matching')
  await expect(page.getByRole('button', { name: '开始匹配', exact: true })).toBeDisabled()
  await capture(page, 'matching-reopened-desktop')
  resumeModel()
  await waitForRun(api, matchId, 'succeeded')
  await expect(page.locator('.result-card')).not.toHaveCount(0)
  await capture(page, 'matching-result-desktop')
  await capture(page, 'matching-result-mobile', true)
  const summary = (await taskSnapshot(api, matchId)).result
  const candidateId = summary.candidates[0].candidate_id

  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto('/questions')
  await expect(page.locator('select').nth(2).locator('option')).not.toHaveCount(1)
  await page.locator('select').nth(0).selectOption(`jd:${jobId}`)
  await page.locator('select').nth(1).selectOption(document.id)
  await page.locator('select').nth(2).selectOption(`${summary.run_id}:${candidateId}`)
  await page.getByRole('spinbutton').fill('3')
  pauseModel()
  const acceptedQuestions = page.waitForResponse(r => r.url().includes('/questions?') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '开始生成', exact: true }).click()
  const questionId = (await (await acceptedQuestions).json()).taskId
  await modelStarted()
  await page.reload()
  await expect(page.getByRole('button', { name: '开始生成', exact: true })).toBeDisabled()
  await expect(page.locator('select').nth(0)).toHaveValue(`jd:${jobId}`)
  await expect(page.locator('select').nth(1)).toHaveValue(document.id)
  await expect(page.locator('select').nth(2)).toHaveValue(`${summary.run_id}:${candidateId}`)
  await expect(page.getByRole('spinbutton')).toHaveValue('3')
  await capture(page, 'questions-reopened-mobile', true)
  resumeModel()
  await waitForRun(api, questionId, 'succeeded')
  await expect(page.locator('.question-card').first()).toBeVisible()
  await capture(page, 'questions-result-desktop')
  await capture(page, 'questions-result-mobile', true)
  await page.goto(`/agent/tasks/${questionId}`)
  await expect(page.getByRole('region', { name: '本次任务结果' })).toContainText('第1项接口设计决定')
  await capture(page, 'questions-saved-task-mobile', true)
  await page.reload()
  await expect(page.getByRole('heading', { name: '出题已完成', exact: true })).toBeVisible()
})

test('保存岗位解析在刷新及网络断开后恢复进度', async ({ page, api }) => {
  test.setTimeout(75_000)
  const jobId = await savedJob(api)
  await page.goto('/jobs')
  await page.locator(`[data-job-id="${jobId}"]`).click()
  pauseModel()
  const accepted = page.waitForResponse(r => r.url().endsWith(`/api/jobs/${jobId}/parse`) && r.request().method() === 'POST')
  await page.getByRole('button', { name: '解析岗位', exact: true }).click()
  const taskId = (await (await accepted).json()).taskId
  await modelStarted()
  await page.reload()
  await expect(page.getByRole('button', { name: '正在解析…', exact: true })).toBeDisabled()
  await capture(page, 'job-parse-reopened-desktop')
  await page.context().setOffline(true)
  await expect(page.getByText('网络连接已断开，正在重新连接。任务会继续运行。', { exact: true })).toBeVisible()
  await capture(page, 'job-parse-offline-mobile', true)
  await page.context().setOffline(false)
  resumeModel()
  await waitForRun(api, taskId, 'succeeded')
  await expect(page.getByRole('link', { name: '去匹配', exact: true })).toBeVisible()
  await capture(page, 'job-parse-restored-mobile', true)
})

test('解析失败和取消保留原件，回答分析显示保存的结果', async ({ page, api }) => {
  test.setTimeout(100_000)
  const failedId = await upload(api, `${resumeText}\nE2E_ALWAYS_FAIL`, '解析失败仍保留原件的长文件名.txt')
  await waitForRun(api, failedId, 'failed')
  const failedRun = await taskSnapshot(api, failedId)
  const failedDocument = await api.get(`/api/documents/${failedRun.input.documentId}`)
  expect(failedDocument.status()).toBe(200)
  expect((await failedDocument.json()).local_stored).toBe(true)
  await page.goto(`/agent/tasks/${failedId}`)
  await expect(page.getByRole('heading', { name: '解析未完成', exact: true })).toBeVisible()
  await capture(page, 'parse-failed-desktop')
  await capture(page, 'parse-failed-mobile', true)

  pauseModel()
  const cancelledId = await upload(api, `${resumeText}\n本任务用于取消后保留原件。`, '取消后保留的简历.txt')
  await modelStarted()
  expect((await api.post(`/api/agent/runs/${cancelledId}/cancel`, { data: {} })).ok()).toBe(true)
  resumeModel()
  await waitForRun(api, cancelledId, 'cancelled')
  const cancelledRun = await taskSnapshot(api, cancelledId)
  expect((await (await api.get(`/api/documents/${cancelledRun.input.documentId}`)).json()).parse_status).toBe('cancelled')
  await page.goto(`/agent/tasks/${cancelledId}`)
  await expect(page.getByRole('heading', { name: '解析已取消', exact: true })).toBeVisible()
  await capture(page, 'parse-cancelled-mobile', true)

  const response = await api.post('/api/followups/analyze', { headers: { Prefer: 'respond-async' }, data: { question: '你怎样定位接口问题？', answer: '先核对日志，再验证接口响应，记录尚未确认的指标。', history: [] } })
  expect(response.status()).toBe(202)
  const followupId = (await response.json()).taskId
  await waitForRun(api, followupId, 'succeeded')
  await page.goto(`/agent/tasks/${followupId}`)
  await expect(page.getByRole('region', { name: '本次任务结果' })).toContainText('当时如何确认接口已经恢复')
  await capture(page, 'followup-result-desktop')
  await capture(page, 'followup-result-mobile', true)
})
