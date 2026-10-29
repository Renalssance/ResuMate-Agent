import { test, expect, createRun, waitForRun, snapshot } from './support/fixtures'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import type { Page } from '@playwright/test'

async function capture(page: Page, name: string, mobile = false, selector?: string) {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1100 })
  if (mobile) {
    const openMenu = page.getByRole('button', { name: '打开导航', exact: true })
    await expect(openMenu).toBeVisible()
    if (await openMenu.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '主导航', exact: true })).toBeHidden()
  }
  await page.evaluate(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    await Promise.all(document.getAnimations().filter(animation => Number.isFinite(animation.effect?.getComputedTiming().endTime)).map(animation => animation.finished.catch(() => {})))
    window.scrollTo(0, 0)
  })
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  if (selector) {
    const card = page.locator(selector)
    const box = await card.boundingBox()
    expect(box).not.toBeNull()
    await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, clip: box!, animations: 'disabled' })
  } else {
    await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
  }
}

test('真实设置保存区分容量与输出，缺配置和超预算给出可行动说明', async ({ page, api }) => {
  expect((await api.put('/api/settings/llm', { data: { context_window_tokens: null } })).ok()).toBeTruthy()
  try {
    await page.goto('/settings')
    await expect(page.locator('.settings-config-card')).toContainText('上下文容量')
    await capture(page, 'capacity-unconfigured-desktop', false, '.settings-config-card')
    const missingRun = await createRun(api, 'failed')
    expect((await snapshot(api, missingRun)).errorCode).toBe('model_context_not_configured')
    await page.goto(`/agent/tasks/${missingRun}`)
    await expect(page.locator('.task-detail').getByRole('link', { name: /设置/ })).toBeVisible()
    await capture(page, 'capacity-missing-mobile', true, '.task-detail')
    await page.goto('/settings')
    await page.locator('.settings-config-card').getByRole('button', { name: /编辑|配置模型/ }).click()
    await page.locator('#settings-context-window').fill('4000')
    await page.getByLabel('输出 Token 上限', { exact: true }).fill('4096')
    await page.locator('.settings-config-card').getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.locator('.settings-config-card')).toContainText('大于')
    await capture(page, 'capacity-validation-mobile', true, '.settings-config-card')
    await page.locator('#settings-context-window').fill('64000')
    await page.locator('.settings-config-card').getByRole('button', { name: '保存', exact: true }).click()
    await expect(page.locator('#settings-context-window')).toBeHidden()
    await expect(page.locator('.settings-config-card')).toContainText('64,000')
    await capture(page, 'capacity-configured-desktop', false, '.settings-config-card')
    expect((await api.put('/api/settings/llm', { data: { context_window_tokens: 6000, max_tokens: 1000 } })).ok()).toBeTruthy()
    const exhausted = await createRun(api, 'failed')
    expect((await snapshot(api, exhausted)).errorCode).toBe('context_budget_exceeded')
    await page.goto(`/agent/tasks/${exhausted}`)
    await expect(page.locator('.task-detail')).toContainText('上下文')
    await capture(page, 'context-budget-error-mobile', true, '.task-detail')
  } finally {
    expect((await api.put('/api/settings/llm', { data: { context_window_tokens: 64000, max_tokens: 4096 } })).ok()).toBeTruthy()
  }
})

test('确认保存长记忆、刷新保留、删除清理和旧任务隔离', async ({ page, api }) => {
  const infrastructure = JSON.parse(readFileSync(join(process.env.RESUMATE_E2E_ROOT!, 'fixture.json'), 'utf8'))
  let memoryId = '', workerStopped = false
  try {
    await page.goto('/profile-fields')
    const card = page.locator('.business-memory')
    await expect(card).toBeVisible()
    await capture(page, 'memory-empty-desktop', false, '.business-memory')
    const content = '请使用中文简短表达；不要把岗位要求写成我的经历。' + '反馈仅供练习：回答需要说明本人负责的部分，未测量的指标不填写。'.repeat(18)
    await page.getByLabel('记忆内容', { exact: true }).fill(content)
    const save = card.getByRole('button', { name: '保存记忆', exact: true })
    await expect(save).toBeDisabled()
    await card.locator('input[data-memory-confirm]').check()
    await page.route('**/api/memories', route => route.request().method() === 'POST' ? route.abort('failed') : route.continue())
    await save.click()
    await expect(card.getByRole('alert')).toBeVisible()
    await expect(page.getByLabel('记忆内容', { exact: true })).toHaveValue(content)
    await capture(page, 'memory-save-error-mobile', true, '.business-memory')
    await page.unroute('**/api/memories')
    await save.click()
    await expect(card).toContainText(content)
    const saved = await (await api.get('/api/memories')).json()
    expect(saved.items).toHaveLength(1)
    memoryId = saved.items[0].id
    await page.reload()
    await expect(card).toContainText(content)
    await capture(page, 'memory-long-desktop', false, '.business-memory')
    await capture(page, 'memory-long-mobile', true, '.business-memory')
    const runId = await createRun(api)
    const before = await snapshot(api, runId)
    process.kill(infrastructure.workerPid, 'SIGSTOP')
    workerStopped = true
    await card.getByRole('button', { name: '删除记忆', exact: true }).click()
    await expect.poll(async () => (await (await api.get('/api/memories')).json()).items.length).toBe(0)
    const pending = await (await api.get('/api/memories')).json()
    expect(pending.pendingDeletions).toHaveLength(1)
    await expect(card).toContainText('清理')
    await expect(card).not.toContainText(content)
    await capture(page, 'memory-cleanup-pending-mobile', true, '.business-memory')
    await waitForRun(api, runId, 'cancelled')
    expect((await snapshot(api, runId)).errorCode).toBe('session_context_invalidated')
    await page.goto(`/agent/tasks/${runId}`)
    await expect(page.locator('.task-detail')).toContainText('记忆')
    await expect(page.locator('.task-detail').getByRole('button', { name: '重试任务' })).toHaveCount(0)
    await capture(page, 'memory-invalidated-task-mobile', true, '.task-detail')
    const action = before.actions[0]!
    const answer = await api.post(`/api/agent/runs/${runId}/actions/${action.actionId}`, { data: { expectedRevision: action.revision, decision: 'submit', answers: { answer: '旧任务不得恢复' } } })
    expect(answer.status()).toBe(409)
    process.kill(infrastructure.workerPid, 'SIGCONT')
    workerStopped = false
    const scan = spawnSync('.venv/bin/python', ['-c', "from backend.worker import app; app.send_task('resumate.recover_runs')"], {
      env: { ...process.env, REDIS_URL: infrastructure.redisUrl }, encoding: 'utf8', timeout: 10_000,
    })
    expect(scan.status, scan.stderr).toBe(0)
    await expect.poll(async () => (await (await api.get('/api/memories')).json()).pendingDeletions.length).toBe(0)
    await page.goto('/profile-fields')
    await expect(card).not.toContainText(content)
    await capture(page, 'memory-cleanup-complete-desktop', false, '.business-memory')
    const repeated = await (await api.delete(`/api/memories/${memoryId}`)).json()
    expect(repeated.cleanupStatus).toBe('complete')
    const cleanRun = await createRun(api)
    expect(cleanRun).not.toBe(runId)
    expect((await api.post(`/api/agent/runs/${cleanRun}/cancel`)).ok()).toBeTruthy()
  } finally {
    if (workerStopped) process.kill(infrastructure.workerPid, 'SIGCONT')
    if (memoryId) await api.delete(`/api/memories/${memoryId}`)
  }
})

test('历史失败任务撤回记忆后，过期重试转到干净任务入口', async ({ page, api }) => {
  const response = await api.post('/api/memories', { data: {
    kind: 'interview_feedback', content: '练习反馈：先说明本人职责，再解释技术选择；未测量的效果不要补造数字。', confirmed: true,
  } })
  expect(response.ok()).toBeTruthy()
  const memory = await response.json()
  try {
    await page.goto('/profile-fields')
    await expect(page.locator('.business-memory .memory-item')).toContainText('面试反馈')
    await capture(page, 'memory-feedback-desktop', false, '.business-memory')
    expect((await api.put('/api/settings/llm', { data: { context_window_tokens: 6000, max_tokens: 1000 } })).ok()).toBeTruthy()
    const runId = await createRun(api, 'failed')
    await page.goto(`/agent/tasks/${runId}`)
    await expect(page.locator('.task-detail').getByRole('button', { name: '重试任务' })).toBeVisible()
    expect((await api.put('/api/settings/llm', { data: { context_window_tokens: 64000, max_tokens: 4096 } })).ok()).toBeTruthy()
    expect((await api.delete(`/api/memories/${memory.id}`)).ok()).toBeTruthy()
    // The failed page was already open and its terminal SSE closed before deletion.
    await page.locator('.task-detail').getByRole('button', { name: '重试任务' }).click()
    await expect(page.locator('.task-detail').getByRole('button', { name: '重试任务' })).toHaveCount(0)
    await expect(page.locator('.task-detail').getByRole('button', { name: '重新准备材料' })).toBeVisible()
    const current = await (await api.get(`/api/agent/runs/${runId}`)).json()
    expect(current.status).toBe('failed')
    expect(current.errorCode).toBe('context_budget_exceeded')
    expect(current.sessionInvalidated).toBe(true)
    await page.reload()
    await expect(page.locator('.task-detail').getByRole('button', { name: '重试任务' })).toHaveCount(0)
    await expect(page.locator('.task-detail')).toContainText('记忆已删除')
    await capture(page, 'memory-historical-failure-mobile', true, '.task-detail')
    await page.locator('.task-detail').getByRole('button', { name: '重新准备材料' }).click()
    await expect.poll(() => page.url().split('/').pop()).not.toBe(runId)
    const freshId = page.url().split('/').pop()!
    await waitForRun(api, freshId, 'waiting_input')
    const fresh = await (await api.get(`/api/agent/runs/${freshId}`)).json()
    expect(fresh.sessionId).not.toBe(current.sessionId)
    expect(fresh.inputVersions.memories).toEqual([])
    expect((await api.post(`/api/agent/runs/${freshId}/cancel`)).ok()).toBeTruthy()
  } finally {
    await api.put('/api/settings/llm', { data: { context_window_tokens: 64000, max_tokens: 4096 } })
    await api.delete(`/api/memories/${memory.id}`)
  }
})
