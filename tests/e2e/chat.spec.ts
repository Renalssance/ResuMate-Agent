import { test, expect, waitForRun } from './support/fixtures'

test('聊天创建真实材料任务、刷新后补问并读取草稿', async ({ page, api }) => {
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.goto('/chat')
  const materialTrigger = page.getByRole('button', { name: '添加材料', exact: true })
  const materialPanel = page.getByRole('dialog', { name: '添加材料', exact: true })
  await page.getByLabel('给米洛的消息').focus()
  await page.keyboard.press('Tab')
  await expect(materialTrigger).toBeFocused()
  await expect(materialTrigger).toHaveAccessibleName('添加材料')
  await page.keyboard.press('Enter')
  await expect(materialPanel).toBeVisible()
  await expect(materialPanel).toHaveCSS('opacity', '1')
  const pickerGeometry = await page.evaluate(() => {
    const trigger = document.querySelector('.material-trigger')!.getBoundingClientRect()
    const panel = document.querySelector('.material-panel')!.getBoundingClientRect()
    return {
      centerDelta: Math.abs(trigger.left + trigger.width / 2 - panel.left - panel.width / 2),
      gap: trigger.top - panel.bottom,
      insideViewport: panel.left >= 0 && panel.right <= window.innerWidth && panel.top >= 0 && panel.bottom <= window.innerHeight,
    }
  })
  expect(pickerGeometry.centerDelta).toBeLessThan(2)
  expect(pickerGeometry.gap).toBeGreaterThanOrEqual(7)
  expect(pickerGeometry.gap).toBeLessThanOrEqual(9)
  expect(pickerGeometry.insideViewport).toBe(true)
  await page.keyboard.press('Escape')
  await expect(materialPanel).toBeHidden()
  await materialTrigger.click()
  await page.getByRole('button', { name: '选择数据库中的简历' }).click()
  await page.getByRole('button', { name: 'E2E 主简历.txt', exact: true }).click()
  await expect(materialPanel).toBeHidden()
  await materialTrigger.click()
  await page.getByRole('button', { name: '选择数据库中的岗位' }).click()
  await page.getByRole('button', { name: 'API 工程师', exact: true }).click()
  await expect(materialPanel).toBeHidden()
  await page.getByLabel('给米洛的消息').fill('请根据所选简历和岗位准备一份简历草稿。')
  const accepted = page.waitForResponse(r => r.url().endsWith('/messages') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  const response = await accepted
  expect(response.status(), await response.text()).toBe(202)
  const { runId } = await response.json()
  await waitForRun(api, runId, 'succeeded')
  await expect(page).toHaveURL(/\/chat\/[^/]+$/)
  const chatUrl = page.url()
  const state = await (await api.get(`/api/agent/runs/${runId}`)).json()
  const child = state.outputRefs.find((ref: {type:string}) => ref.type === 'run').id
  await waitForRun(api, child, 'waiting_input')
  await expect(page.getByRole('link', { name: '补充信息并继续', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('任务已受理，可以在卡片中查看进度。', { exact: true })).toBeVisible()
  await page.getByLabel('给米洛的消息').fill(`任务 ${child} 补充：我负责 API 和数据库设计。`)
  const continued = page.waitForResponse(r => r.url().endsWith('/messages') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  const next = await continued
  expect(next.status()).toBe(202)
  await waitForRun(api, (await next.json()).runId, 'succeeded')
  const completed = await waitForRun(api, child, 'succeeded')
  expect(completed.outputRefs.some(ref => ref.type === 'resume_version')).toBe(true)
  await page.reload()
  await expect(page).toHaveURL(chatUrl)
  await expect(page.getByText('我负责 API 和数据库设计。', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /继续分析/ }).first()).toBeVisible()
  const desktopComposerLayout = await page.evaluate(() => {
    const conversation = document.querySelector('.chat-conversation')!.getBoundingClientRect()
    const composer = document.querySelector('.chat-composer')!.getBoundingClientRect()
    return {
      overlap: conversation.bottom - composer.top,
      composerHeight: composer.height,
    }
  })
  expect(desktopComposerLayout.overlap).toBeGreaterThan(desktopComposerLayout.composerHeight * 0.35)
  expect(desktopComposerLayout.overlap).toBeLessThan(desktopComposerLayout.composerHeight * 0.7)
  await page.screenshot({ path: test.info().outputPath('chat-desktop.png'), fullPage: true, animations: 'disabled' })
  for (const width of [900, 390]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(page.getByRole('button', { name: '打开导航', exact: true })).toBeVisible()
    await expect(page.getByRole('dialog', { name: '主导航', exact: true })).toBeHidden()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await materialTrigger.click()
    await expect(materialPanel).toBeVisible()
    await expect(materialPanel).toHaveCSS('opacity', '1')
    const pickerLayout = await page.evaluate(() => {
      const trigger = document.querySelector('.material-trigger')!.getBoundingClientRect()
      const panel = document.querySelector('.material-panel')!.getBoundingClientRect()
      const conversation = document.querySelector('.chat-conversation')!.getBoundingClientRect()
      const composer = document.querySelector('.chat-composer')!.getBoundingClientRect()
      return {
        centerDelta: Math.abs(trigger.left + trigger.width / 2 - panel.left - panel.width / 2),
        gap: trigger.top - panel.bottom,
        insideViewport: panel.left >= 0 && panel.right <= window.innerWidth && panel.top >= 0 && panel.bottom <= window.innerHeight,
        overlap: conversation.bottom - composer.top,
        composerHeight: composer.height,
      }
    })
    expect(pickerLayout.centerDelta).toBeLessThan(2)
    expect(pickerLayout.gap).toBeGreaterThanOrEqual(7)
    expect(pickerLayout.gap).toBeLessThanOrEqual(9)
    expect(pickerLayout.insideViewport, `${width}px picker stays inside viewport`).toBe(true)
    expect(pickerLayout.overlap).toBeGreaterThan(0)
    expect(pickerLayout.overlap).toBeLessThan(pickerLayout.composerHeight)
    await page.keyboard.press('Escape')
    await expect(materialPanel).toBeHidden()
    await page.screenshot({ path: test.info().outputPath(width === 390 ? 'chat-mobile.png' : 'chat-tablet.png'), fullPage: true, animations: 'disabled' })
  }
})
