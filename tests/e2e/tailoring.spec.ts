import { test, expect, createRun, waitForRun } from './support/fixtures'
import type { Page } from '@playwright/test'

async function captureCard(page: Page, name: string, mobile = false) {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1100 })
  if (mobile) {
    const menu = page.getByRole('button', { name: '打开导航', exact: true })
    await expect(menu).toBeVisible()
    if (await menu.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '主导航', exact: true })).toBeHidden()
  }
  const card = page.locator('.artifact-card').first()
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const box = await card.boundingBox()
  expect(box).not.toBeNull()
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), clip: box!, fullPage: true, animations: 'disabled' })
}

test('任务固定旧资料，草稿逐项展示来源、补问与缺失信息', async ({ page, api }) => {
  const originalResponse = await api.get('/api/documents/resume:1')
  expect(originalResponse.status()).toBe(200)
  const original = (await originalResponse.json()).parsed_content
  const factResponse = await api.post('/api/profile-facts', { data: {
    kind: 'experience', content: { text: '负责 API 与数据库结构设计，未提供用户规模指标。' },
    sourceDocumentId: 1, confirmed: true,
  } })
  expect(factResponse.status()).toBe(200)
  const fact = await factResponse.json()
  const runId = await createRun(api)
  const changed = await api.patch('/api/documents/resume:1/structured-data', {
    data: { structured_data: { ...original, summary: '任务开始后的新简介，不得混入旧建议。' } },
  })
  expect(changed.status()).toBe(200)
  try {
    await page.goto(`/agent/tasks/${runId}`)
    await page.getByLabel('你负责什么工作？', { exact: true }).fill('负责 API 设计、数据库模型与接口联调。')
    await page.getByRole('button', { name: '继续任务' }).click()
    const run = await waitForRun(api, runId, 'succeeded')
    await expect(page.locator('.artifact-card')).toBeVisible()
    const artifactResponse = await api.get(`/api/resume-versions/${run.outputRefs[0].id}`)
    expect(artifactResponse.status()).toBe(200)
    const artifact = await artifactResponse.json()
    expect(artifact.basedOnOldInput).toBe(true)
    expect(artifact.changedInputs).toContain('resume')
    expect(artifact.structuredContent.resume.summary).toBe(original.summary)
    expect(artifact.structuredContent.changes).toHaveLength(2)
    expect(artifact.structuredContent.changes[0].before).toBe(original.summary)
    expect(artifact.structuredContent.changes[1].requires_input).toBe(true)
    expect(artifact.structuredContent.changes[1].after).toBeNull()
    expect(artifact.sources.map((source: { reference: { kind: string } }) => source.reference.kind))
      .toEqual(expect.arrayContaining(['resume', 'profile_fact', 'applicant_answer']))
    await expect(page.locator('.artifact-card')).not.toContainText('任务开始后的新简介')
    await expect(page.locator('.artifact-card')).toContainText('API development')
    await expect(page.locator('.artifact-card').getByRole('note')).toContainText('这份草稿依据旧资料生成')
    await expect(page.locator('.artifact-card')).toContainText('补充事实后再形成建议')
    await expect(page.locator('.artifact-card')).toContainText('负责 API 与数据库结构设计')
    await expect(page.locator('.artifact-card')).toContainText('负责 API 设计、数据库模型与接口联调')
    await captureCard(page, 'evidence-old-input-desktop')
    await captureCard(page, 'evidence-old-input-mobile', true)
    await page.reload()
    await expect(page.locator('.artifact-card')).toContainText('API development')
    const repeated = await api.get(`/api/agent/runs/${runId}/artifacts`)
    expect((await repeated.json())).toHaveLength(1)
  } finally {
    const restored = await api.patch('/api/documents/resume:1/structured-data', { data: { structured_data: original } })
    expect(restored.status()).toBe(200)
    const removed = await api.delete(`/api/profile-facts/${fact.id}?expectedRevision=1`)
    expect(removed.status()).toBe(200)
  }
})
