import { test, expect, createRun, snapshot, waitForRun } from './support/fixtures'
import type { APIRequestContext, Page } from '@playwright/test'

const summaryName = '个人简介建议'
const workName = '工作经历 1 · 经历说明建议'
const editedWork = '负责 API 设计、数据库结构与接口联调；与团队一起核对需求并维护接口文档。'.repeat(4)

async function prepare(api: APIRequestContext) {
  const runId = await createRun(api)
  const run = await snapshot(api, runId)
  const answer = await api.post(`/api/agent/runs/${runId}/actions/${run.actions[0]!.actionId}`, {
    data: { decision: 'submit', answers: { answer: '负责 API 和数据库设计，与团队核对需求。' }, expectedRevision: 1 },
  })
  expect(answer.status()).toBe(202)
  return (await waitForRun(api, runId, 'succeeded')).outputRefs[0]!.id
}
async function capture(page: Page, name: string, mobile = false) {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1100 })
  if (mobile) {
    const menu = page.getByRole('button', { name: '打开导航', exact: true })
    await expect(menu).toBeVisible()
    if (await menu.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '主导航', exact: true })).toBeHidden()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
}
async function save(page: Page, versionId: string, status = 200) {
  const response = page.waitForResponse(r => r.url().endsWith(`/api/resume-versions/${versionId}`) && r.request().method() === 'PATCH')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  expect((await response).status()).toBe(status)
}

test('逐项接受撤销和本人编辑，离开保留输入，保存确认不改主简历', async ({ page, api }) => {
  const versionId = await prepare(api)
  const original = await (await api.get('/api/documents/resume:1')).json()
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto(`/resume-versions/${versionId}`)
  await expect(page.getByRole('link', { name: '材料准备', exact: true })).toHaveClass(/router-link-active/)
  const summary = page.getByRole('region', { name: summaryName, exact: true })
  const work = page.getByRole('region', { name: workName, exact: true })
  await summary.getByRole('button', { name: '接受建议', exact: true }).click()
  await summary.getByRole('button', { name: '撤销决定', exact: true }).click()
  await summary.getByRole('button', { name: '接受建议', exact: true }).click()
  await expect(work.getByRole('button', { name: '接受建议', exact: true })).toBeDisabled()
  await work.getByRole('button', { name: '编辑内容', exact: true }).click()
  await page.getByRole('textbox', { name: /^编辑工作经历 1 · 经历说明/ }).fill(editedWork)
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('link', { name: /返回材料准备$/ }).click()
  await expect(page).toHaveURL(`/resume-versions/${versionId}`)
  await expect(page.getByRole('textbox', { name: /^编辑工作经历 1 · 经历说明/ })).toHaveValue(editedWork)
  await capture(page, 'review-long-desktop')
  await capture(page, 'review-long-mobile', true)
  await save(page, versionId)
  const stored = await (await api.get(`/api/resume-versions/${versionId}`)).json()
  expect(stored.revision).toBe(2)
  expect(stored.structuredContent.changes.map((c: { status: string }) => c.status)).toEqual(['accepted', 'edited'])
  expect(stored.structuredContent.resume.work_experience[0].description).toBe(editedWork)
  const confirmedResponse = page.waitForResponse(r => r.url().endsWith(`/api/resume-versions/${versionId}/confirm`))
  await page.getByRole('button', { name: '确认版本', exact: true }).click()
  expect((await confirmedResponse).status()).toBe(200)
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toHaveCount(0)
  await capture(page, 'review-confirmed-mobile', true)
  const confirmed = await (await api.get(`/api/resume-versions/${versionId}`)).json()
  expect(confirmed.status).toBe('confirmed')
  expect(confirmed.revision).toBe(3)
  const mainResume = await (await api.get('/api/documents/resume:1')).json()
  expect(mainResume.parsed_content).toEqual(original.parsed_content)
  const blocked = await api.patch(`/api/resume-versions/${versionId}`, { data: {
    expectedRevision: confirmed.revision,
    changes: confirmed.structuredContent.changes.map((c: { id: string }) => ({ id: c.id, status: 'rejected' })),
  } })
  expect(blocked.status()).toBe(409)
})

test('两个页面冲突后保留本地输入，只重放本人改过的条目', async ({ page, context, api }) => {
  const versionId = await prepare(api)
  const other = await context.newPage()
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto(`/resume-versions/${versionId}`)
  await other.goto(`/resume-versions/${versionId}`)
  await expect(page.getByRole('region', { name: summaryName, exact: true })).toBeVisible()
  const work = page.getByRole('region', { name: workName, exact: true })
  await work.getByRole('button', { name: '编辑内容', exact: true }).click()
  await page.getByRole('textbox', { name: /^编辑工作经历 1 · 经历说明/ }).fill('这页补充 API 联调职责，另一页的拒绝决定必须保留。')
  await other.getByRole('region', { name: summaryName, exact: true }).getByRole('button', { name: '拒绝建议', exact: true }).click()
  await save(other, versionId)
  await save(page, versionId, 409)
  await expect(page.getByRole('textbox', { name: /^编辑工作经历 1 · 经历说明/ })).toHaveValue('这页补充 API 联调职责，另一页的拒绝决定必须保留。')
  await expect(page.locator('summary').filter({ hasText: '服务器最新版本' })).toBeVisible()
  await capture(page, 'review-conflict-desktop')
  await capture(page, 'review-conflict-mobile', true)
  await page.getByRole('button', { name: '将我的修改应用到最新版本', exact: true }).click()
  await save(page, versionId)
  const merged = await (await api.get(`/api/resume-versions/${versionId}`)).json()
  expect(merged.revision).toBe(3)
  expect(merged.structuredContent.changes.map((c: { status: string }) => c.status)).toEqual(['rejected', 'edited'])
  expect(merged.structuredContent.resume.summary).toBe('API development')
  await other.close()
})

test('不存在的简历版本显示可恢复加载错误', async ({ page, api }) => {
  void api
  await page.goto('/resume-versions/missing-version')
  await expect(page.getByRole('alert')).toContainText('不存在')
  await capture(page, 'review-load-error-mobile', true)
})
