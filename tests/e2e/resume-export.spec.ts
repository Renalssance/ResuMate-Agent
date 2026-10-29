import { test, expect, createRun, snapshot, waitForRun } from './support/fixtures'
import type { APIRequestContext, Page } from '@playwright/test'
import { writeFileSync, rmSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

async function confirmedVersion(api: APIRequestContext) {
  const runId = await createRun(api)
  const run = await snapshot(api, runId)
  const answer = await api.post(`/api/agent/runs/${runId}/actions/${run.actions[0]!.actionId}`, { data: {
    decision: 'submit', answers: { answer: '负责 API 设计、数据库模型与接口联调。' }, expectedRevision: 1,
  } })
  expect(answer.status()).toBe(202)
  const done = await waitForRun(api, runId, 'succeeded')
  const id = done.outputRefs[0]!.id
  const version = await (await api.get(`/api/resume-versions/${id}`)).json()
  const saved = await api.patch(`/api/resume-versions/${id}`, { data: { expectedRevision: 1,
    changes: version.structuredContent.changes.map((c: { id: string; requires_input: boolean }) => ({
      id: c.id, status: c.requires_input ? 'rejected' : 'accepted',
    })),
  } })
  expect(saved.status()).toBe(200)
  const confirmed = await api.post(`/api/resume-versions/${id}/confirm`, { data: { expectedRevision: 2 } })
  expect(confirmed.status()).toBe(200)
  return confirmed.json()
}
async function capture(page: Page, name: string, mobile = false) {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1100 })
  if (mobile) {
    const menu = page.getByRole('button', { name: '打开导航', exact: true })
    if (await menu.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
}
async function startExport(page: Page, versionId: string) {
  const response = page.waitForResponse(r => r.url().endsWith(`/api/resume-versions/${versionId}/export`))
  await page.getByRole('button', { name: '导出 PDF', exact: true }).click()
  const accepted = await response
  expect(accepted.status()).toBe(202)
  const { runId } = await accepted.json()
  await expect(page).toHaveURL(`/agent/tasks/${runId}`)
  return runId as string
}
async function downloadPdf(page: Page, fileName: string) {
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 PDF', exact: true }).click()
  const download = await pending
  const path = test.info().outputPath(fileName)
  await download.saveAs(path)
  expect(readFileSync(path).subarray(0, 5).toString()).toBe('%PDF-')
  const text = execFileSync(join(process.cwd(), '.venv/bin/python'), ['-c',
    'import sys,pymupdf; d=pymupdf.open(sys.argv[1]); print("".join(p.get_text() for p in d))', path], { encoding: 'utf8' })
  expect(text).toContain('示例求职者')
  expect(text).toContain('API')
  return text
}

test('确认版本真实导出PDF，关联新投递后主简历修改不改变提交快照', async ({ page, api }) => {
  const version = await confirmedVersion(api)
  await page.goto(`/resume-versions/${version.id}`)
  const pause = join(process.env.RESUMATE_E2E_ROOT!, 'pdf-pause')
  writeFileSync(pause, '')
  let exportRun: string
  try {
    exportRun = await startExport(page, version.id)
    await expect.poll(async () => (await snapshot(api, exportRun)).status).toBe('running')
    await capture(page, 'pdf-running-desktop')
  } finally { rmSync(pause, { force: true }) }
  await waitForRun(api, exportRun!, 'succeeded')
  await expect(page.getByRole('button', { name: '下载 PDF', exact: true })).toBeVisible()
  await capture(page, 'pdf-ready-desktop')
  await capture(page, 'pdf-ready-mobile', true)
  const pdfText = await downloadPdf(page, 'downloaded-resume.pdf')
  await page.goto(`/resume-versions/${version.id}`)
  await page.getByRole('link', { name: '关联投递', exact: true }).click()
  await expect(page).toHaveURL(/\/applications\?/)
  await expect(page.getByText('关联已确认版本', { exact: true })).toBeVisible()
  await capture(page, 'submission-ready-mobile', true)
  await page.getByRole('button', { name: '新建投递并关联', exact: true }).click()
  const localDate = await page.evaluate(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` })
  await expect(page.getByLabel('投递日期', { exact: true })).toHaveValue(localDate)
  const company = 'T11 示例科技有限公司（长名称用于手机边界检查）'
  await page.getByLabel('公司', { exact: true }).fill(company)
  await page.getByLabel('岗位', { exact: true }).fill('全栈开发工程师')
  const createdResponse = page.waitForResponse(r => r.url().endsWith('/api/applications') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '添加并关联', exact: true }).click()
  const created = await createdResponse
  expect(created.status()).toBe(200)
  const application = await created.json()
  expect(application.resume_version_id).toBe(version.id)
  expect(application.submitted_snapshot.structuredContent).toEqual(version.structuredContent)
  const original = (await (await api.get('/api/documents/resume:1')).json()).parsed_content
  try {
    expect((await api.patch('/api/documents/resume:1/structured-data', { data: {
      structured_data: { ...original, candidate_name: '后续改名不得混入历史材料', summary: '修改后的新材料' },
    } })).status()).toBe(200)
    await page.reload()
    await page.getByRole('button', { name: '查看提交时材料', exact: true }).first().click()
    await expect(page.getByText('示例求职者', { exact: true })).toBeVisible()
    await expect(page.locator('body')).not.toContainText('后续改名不得混入历史材料')
    await capture(page, 'submission-snapshot-mobile', true)
    for (const label of ['收起提交时材料', '编辑', '记录', '日程', '时间线', '删除']) {
      const button = page.getByRole('button', { name: label, exact: true }).first()
      const box = await button.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(390)
    }
    await capture(page, 'submission-snapshot-desktop')
    const records = await (await api.get('/api/applications')).json()
    const items = Array.isArray(records) ? records : records.items
    expect(items.find((a: { id: number }) => a.id === application.id).submitted_snapshot).toEqual(application.submitted_snapshot)
    expect(pdfText).not.toContain('后续改名不得混入历史材料')
  } finally {
    await api.patch('/api/documents/resume:1/structured-data', { data: { structured_data: original } })
  }
})

test('真实渲染失败后可重试并下载，已有旧投递可关联确认版本', async ({ page, api }) => {
  const version = await confirmedVersion(api)
  const legacy = await api.post('/api/applications', { data: {
    company: 'T11 旧记录公司', position: '接口开发', applied_date: '2026-10-30', status: 'applied',
  } })
  expect(legacy.status()).toBe(200)
  const application = await legacy.json()
  expect(application.submitted_snapshot).toBeNull()
  writeFileSync(join(process.env.RESUMATE_E2E_ROOT!, 'pdf-fail-once'), '')
  await page.goto(`/resume-versions/${version.id}`)
  const runId = await startExport(page, version.id)
  await waitForRun(api, runId, 'failed')
  await expect(page.getByRole('button', { name: '重试任务', exact: true })).toBeVisible()
  await capture(page, 'pdf-failed-mobile', true)
  await page.getByRole('button', { name: '重试任务', exact: true }).click()
  await waitForRun(api, runId, 'succeeded')
  await downloadPdf(page, 'retried-resume.pdf')
  await page.goto(`/resume-versions/${version.id}`)
  await page.getByRole('link', { name: '关联投递', exact: true }).click()
  await page.getByLabel('已有投递', { exact: true }).selectOption(String(application.id))
  const linkedResponse = page.waitForResponse(r => r.url().endsWith(`/api/applications/${application.id}/submission`))
  await page.getByRole('button', { name: '关联到此投递', exact: true }).click()
  expect((await linkedResponse).status()).toBe(200)
  await expect(page.locator('.application-company-group').filter({ hasText: 'T11 旧记录公司' }).getByRole('button', { name: '查看提交时材料', exact: true })).toBeVisible()
})
