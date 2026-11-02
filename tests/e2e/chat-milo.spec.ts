import { test, expect, type Page } from '@playwright/test'

const session = { sessionId: 'milo-preview', title: '项目经历建议', createdAt: '2026-10-31', updatedAt: '2026-10-31', activeRunId: null }
const answer = '当然可以。我先帮你把这段经历的重点梳理出来。\n\n### 先把你的贡献说清楚\n你负责了什么、做了哪些关键判断，比罗列工作事项更有说服力。\n\n### 把过程写成结果\n补充真实的使用反馈或业务变化，让招聘方看见项目价值。\n\n### 贴近目标岗位\n突出需求分析、跨团队推进和迭代复盘的经历。'

async function freezeHandoff(page: Page) {
  // Freeze the real WAAPI animations at their midpoint, rather than mocking animation APIs.
  await page.evaluate(() => {
    const observe = () => {
      const mascot = document.querySelector('body > .welcome-milo')
      if (!mascot?.getAnimations().length) { requestAnimationFrame(observe); return }
      for (const animation of document.getAnimations()) {
        if ((animation.effect as KeyframeEffect)?.target instanceof HTMLElement) {
          const target = (animation.effect as KeyframeEffect).target as HTMLElement
          if (target.closest('.chat-workspace') || target.closest('body > .welcome-milo') || target.matches('body > .welcome-copy, body > .chat-suggestions')) {
            animation.pause(); animation.currentTime = Math.min(140, Number(animation.effect!.getTiming().duration))
          }
        }
      }
    }
    requestAnimationFrame(observe)
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('accessToken', 'milo-visual-test')
    localStorage.setItem('username', 'Milo')
    localStorage.setItem('resumate:appearance-style', 'glass')
  })
  let sent = false
  await page.route(/^http:\/\/[^/]+\/api\//, async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/runs/milo-run/events')) {
      await route.fulfill({ contentType: 'text/event-stream', body: `event: run.event\ndata: ${JSON.stringify({ runId: 'milo-run', seq: 1, type: 'run.status', createdAt: '', payload: { status: 'succeeded' } })}\n\n` })
      return
    }
    let body: unknown = []
    if (path.endsWith('/messages')) { sent = true; body = { runId: 'milo-run', status: 'queued' } }
    else if (path.endsWith('/sessions')) body = route.request().method() === 'POST' ? session : [session]
    else if (path.endsWith('/sessions/milo-preview')) body = { ...session, turns: sent ? [{ runId: 'milo-run', message: '我想投递产品经理岗位，能帮我看看这段项目经历吗？', status: 'succeeded', text: answer, result: { text: answer }, lastSeq: 1, tools: [], outputRefs: [], errorCode: null }] : [] }
    else if (path.endsWith('/runs/milo-run')) body = { runId: 'milo-run', status: 'succeeded', lastSeq: 1, actions: [], outputRefs: [] }
    else if (path.includes('settings')) body = { model: 'deepseek-v4.1-flash' }
    await route.fulfill({ json: body })
  })
})

test('Milo travels continuously to the reply avatar and the composer lands at the bottom', async ({ page }) => {
  await page.setViewportSize({ width: 1672, height: 940 })
  await page.goto('/chat')
  await expect(page.locator('.welcome-milo img')).toBeVisible()
  await page.locator('.welcome-milo img').evaluate((image: HTMLImageElement) => image.decode())
  const origin = await page.locator('.welcome-milo').boundingBox()
  const composerOrigin = await page.locator('.chat-composer').boundingBox()
  const workspace = await page.locator('.chat-workspace').boundingBox()
  const suggestions = await page.locator('.chat-suggestions').boundingBox()
  expect(Math.abs((origin!.y + suggestions!.y + suggestions!.height) / 2 - (workspace!.y + workspace!.height / 2))).toBeLessThan(20)
  await page.screenshot({ path: test.info().outputPath('milo-welcome.png') })
  await freezeHandoff(page)
  await page.getByLabel('给米洛的消息').fill('我想投递产品经理岗位，能帮我看看这段项目经历吗？')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  const flying = page.locator('body > .welcome-milo')
  await expect(flying).toBeVisible()
  await expect(page.locator('.assistant-avatar')).toHaveCSS('visibility', 'hidden')
  await expect.poll(() => flying.evaluate(el => el.getAnimations()[0]?.playState)).toBe('paused')
  const middle = await flying.boundingBox(), target = await page.locator('.assistant-avatar').boundingBox()
  expect(middle!.width).toBeGreaterThan(target!.width)
  expect(middle!.width).toBeLessThan(origin!.width)
  await page.screenshot({ path: test.info().outputPath('milo-handoff-midpoint.png') })
  await page.evaluate(() => document.getAnimations().forEach(animation => { if (animation.playState === 'paused') animation.finish() }))
  await expect(flying).toHaveCount(0)
  await expect(page.locator('.assistant-avatar')).toBeVisible()
  await expect(page.locator('.assistant-text')).toContainText('先把你的贡献说清楚')
  expect((await page.locator('.chat-composer').boundingBox())!.y).toBeGreaterThan(composerOrigin!.y)
  await page.screenshot({ path: test.info().outputPath('milo-conversation.png') })
})

for (const reducedMotion of ['no-preference', 'reduce'] as const) {
  test(`mobile handoff cleans up on navigation (${reducedMotion})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.emulateMedia({ reducedMotion })
    await page.goto('/chat')
    await expect(page.locator('.welcome-milo')).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await page.getByLabel('给米洛的消息').fill('帮我看看项目经历')
    await page.getByRole('button', { name: '发送消息', exact: true }).click()
    await expect(page.locator('.assistant-avatar')).toBeVisible()
    await expect(page.locator('body > .welcome-milo')).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await page.screenshot({ path: test.info().outputPath(`milo-mobile-${reducedMotion}.png`) })
    await page.locator('.chat-history summary').click()
    await page.getByRole('button', { name: '新对话', exact: true }).click()
    await expect(page.locator('.welcome-milo')).toBeVisible()
    await expect(page.locator('.assistant-avatar')).toHaveCount(0)
    await expect(page.locator('body > .welcome-copy, body > .chat-suggestions')).toHaveCount(0)
  })
}

test('an immediate long reply cannot interrupt the handoff; new chat can', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/chat')
  await expect(page.locator('.welcome-milo')).toBeVisible()
  await freezeHandoff(page)
  await page.getByLabel('给米洛的消息').fill('帮我看看项目经历')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await expect(page.locator('.assistant-text')).toContainText('先把你的贡献说清楚')
  const flying = page.locator('body > .welcome-milo')
  await expect.poll(() => flying.evaluate(el => el.getAnimations()[0]?.playState)).toBe('paused')
  await expect(page.locator('.assistant-avatar')).toHaveCSS('visibility', 'hidden')
  await page.locator('.chat-history summary').click()
  await page.getByRole('button', { name: '新对话', exact: true }).click()
  await expect(flying).toHaveCount(0)
  await expect(page.locator('.welcome-group .welcome-milo')).toBeVisible()
  await expect(page.locator('body > .welcome-copy, body > .chat-suggestions')).toHaveCount(0)
  await expect(page.locator('.chat-composer')).toHaveCSS('transform', 'none')
})
