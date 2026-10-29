import { test, expect, createRun, seededPausedRun, snapshot, waitForRun } from './support/fixtures'
import type { Page } from '@playwright/test'

const question = '你负责什么工作？'
const answer = '负责 API 和数据库设计。' + '与团队核对接口需求、维护数据结构，并以实际项目职责为依据整理待审阅材料。'.repeat(6)
async function capture(page: Page, name: string) {
  if (page.viewportSize()!.width < 1200) {
    await expect(page.getByRole('button', { name: '打开导航', exact: true })).toBeVisible()
    if (await page.getByRole('button', { name: '打开导航', exact: true }).getAttribute('aria-expanded') === 'true') {
      await page.getByRole('button', { name: '关闭导航', exact: true }).click()
    }
    await expect(page.getByRole('dialog', { name: '主导航', exact: true })).toBeHidden()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: page.viewportSize()!.width < 1200 || name.includes('completed'), animations: 'disabled' })
}

// Business responses come from FastAPI, SQL and a separate Celery worker. Routes
// below only control delivery timing or simulate a dropped network connection.
test('页面发起、刷新补问并读取真实 worker 生成的材料', async ({ page, api }) => {
  await page.setViewportSize({ width: 1440, height: 1100 })
  await page.goto('/matching')
  await expect(page.getByRole('heading', { name: '匹配任务配置' })).toBeVisible()
  await capture(page, 'matching-desktop-reference')
  await page.goto('/agent/tasks')
  await expect(page.getByRole('heading', { name: '准备投递材料' })).toBeVisible()
  await capture(page, 'empty-selection-desktop')
  await page.getByLabel('目标岗位').selectOption({ index: 1 })
  await page.getByLabel('主简历').selectOption({ index: 1 })
  const accepted = page.waitForResponse(response => response.url().endsWith('/api/agent/runs') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '开始准备' }).click()
  expect((await accepted).status()).toBe(202)
  await expect(page).toHaveURL(/\/agent\/tasks\/[^/]+$/)
  await expect(page.getByRole('link', { name: '材料准备', exact: true })).toHaveClass(/router-link-active/)
  const runId = page.url().split('/').pop()!
  await expect(page.getByLabel(question, { exact: true })).toBeVisible()
  const before = await snapshot(api, runId)
  expect(before.status).toBe('waiting_input')
  expect(before.actions).toHaveLength(1)
  await page.reload()
  await expect(page.getByLabel(question, { exact: true })).toBeVisible()
  expect((await snapshot(api, runId)).actions[0].actionId).toBe(before.actions[0].actionId)
  await page.getByRole('button', { name: '继续任务' }).click()
  await expect(page.getByRole('alert')).toContainText('请填写补充信息')
  const describedBy = await page.getByLabel(question, { exact: true }).getAttribute('aria-describedby')
  expect(describedBy).toBeTruthy()
  await expect(page.locator(`[id="${describedBy}"]`)).toHaveText('请填写补充信息')
  await page.setViewportSize({ width: 390, height: 844 })
  await capture(page, 'input-validation-mobile')
  await page.reload()
  await page.getByLabel(question, { exact: true }).fill(answer)
  await capture(page, 'waiting-input-mobile')
  await page.setViewportSize({ width: 1440, height: 1100 })
  await capture(page, 'waiting-input-desktop')
  await page.getByRole('button', { name: '继续任务' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  await expect(page.getByText(/API development/).first()).toBeVisible()
  const completed = await waitForRun(api, runId, 'succeeded')
  expect(completed.actions).toHaveLength(0)
  expect(completed.outputRefs).toHaveLength(1)
  expect(completed.cancelRequested).toBe(false)
  await capture(page, 'completed-long-material-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await capture(page, 'completed-long-material-mobile')
})

test('测试入口准备的真实暂停任务可从新页面继续', async ({ page, api }) => {
  const runId = seededPausedRun()
  await page.goto(`/agent/tasks/${runId}`)
  await page.reload()
  await page.getByLabel(question, { exact: true }).fill(answer)
  await page.getByRole('button', { name: '继续任务' }).click()
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  expect((await waitForRun(api, runId, 'succeeded')).outputRefs).toHaveLength(1)
})

test('另一个标签页先回答时旧提交收到 409 并保留输入', async ({ page, context, api }) => {
  const runId = await createRun(api)
  const other = await context.newPage()
  await page.goto(`/agent/tasks/${runId}`)
  await other.goto(`/agent/tasks/${runId}`)
  await page.getByLabel(question, { exact: true }).fill(answer)
  await other.getByLabel(question, { exact: true }).fill('这份输入需要保留')
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let captured!: () => void
  const pending = new Promise<void>(resolve => { captured = resolve })
  await other.route(`**/api/agent/runs/${runId}/actions/*`, async route => {
    captured()
    await gate
    await route.continue()
  })
  const conflict = other.waitForResponse(response => response.url().includes(`/api/agent/runs/${runId}/actions/`) && response.request().method() === 'POST')
  await other.getByRole('button', { name: '继续任务' }).click()
  await pending
  await page.getByRole('button', { name: '继续任务' }).click()
  await waitForRun(api, runId, 'succeeded')
  release()
  expect((await conflict).status()).toBe(409)
  await expect(other.getByText('任务状态已变化，其他页面可能已处理该问题。你的未提交回答已保留。', { exact: true })).toContainText(/已|变化|刷新/)
  await expect(other.getByLabel(question, { exact: true })).toHaveValue('这份输入需要保留')
  await expect(other.getByLabel(question, { exact: true })).toBeFocused()
  await other.close()
})

test('提交后离开页面不会隐式取消 worker，返回可读取产物', async ({ page, api }) => {
  const runId = await createRun(api)
  await page.goto(`/agent/tasks/${runId}`)
  await page.getByLabel(question, { exact: true }).fill(answer)
  const resumed = page.waitForResponse(response => response.url().includes(`/api/agent/runs/${runId}/actions/`))
  await page.getByRole('button', { name: '继续任务' }).click()
  expect((await resumed).status()).toBe(202)
  await page.goto('/agent/tasks')
  const finished = await waitForRun(api, runId, 'succeeded')
  expect(finished.cancelRequested).toBe(false)
  expect(finished.outputRefs).toHaveLength(1)
  await page.goto(`/agent/tasks/${runId}`)
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  await expect(page.getByText(/API development/).first()).toBeVisible()
})

test('等待补问时可明确取消任务', async ({ page, api }) => {
  const runId = await createRun(api)
  await page.goto(`/agent/tasks/${runId}`)
  await page.getByRole('button', { name: '取消任务', exact: true }).click()
  await expect(page.getByRole('heading', { name: '任务已取消', exact: true })).toBeVisible()
  const cancelled = await waitForRun(api, runId, 'cancelled')
  expect(cancelled.cancelRequested).toBe(true)
  expect(cancelled.outputRefs).toHaveLength(0)
})

test('worker 正在执行时明确取消，最终停止且不生成材料', async ({ page, api }) => {
  const runId = await createRun(api, 'running')
  await page.goto(`/agent/tasks/${runId}`)
  const cancelled = page.waitForResponse(response => response.url().endsWith(`/api/agent/runs/${runId}/cancel`))
  await page.getByRole('button', { name: '取消任务', exact: true }).click()
  expect((await cancelled).status()).toBe(202)
  await expect(page.getByRole('heading', { name: '任务已取消', exact: true })).toBeVisible()
  const finished = await waitForRun(api, runId, 'cancelled')
  expect(finished.cancelRequested).toBe(true)
  expect(finished.outputRefs).toHaveLength(0)
})

test('事件网络断线显示重连，任务保持等待并在恢复后继续', async ({ page, api }) => {
  const runId = await createRun(api)
  await page.route(`**/api/agent/runs/${runId}/events*`, route => route.abort('connectionfailed'))
  await page.goto(`/agent/tasks/${runId}`)
  await expect(page.getByText(/网络连接已断开/)).toBeVisible()
  await capture(page, 'network-reconnecting-desktop')
  expect((await snapshot(api, runId)).status).toBe('waiting_input')
  await expect(page.getByText('任务失败', { exact: true })).toHaveCount(0)
  await page.unroute(`**/api/agent/runs/${runId}/events*`)
  await expect(page.getByText(/网络连接已断开/)).toHaveCount(0)
  await page.getByLabel(question, { exact: true }).fill(answer)
  await page.getByRole('button', { name: '继续任务' }).click()
  await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  expect((await waitForRun(api, runId, 'succeeded')).errorCode).toBeNull()
})
