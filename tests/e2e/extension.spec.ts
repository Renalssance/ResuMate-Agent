import { chromium, type BrowserContext, type Page, type Worker, type APIRequestContext } from '@playwright/test'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { test as base, expect, createRun, snapshot, waitForRun } from './support/fixtures'

const API = 'http://127.0.0.1:4174'
const SITE = 'http://127.0.0.1:8899/extension/fixtures'
const frozenWork = '已确认版本：负责 API 设计、数据库模型与接口联调，核对实际接口需求并维护说明。'
interface Extension { context: BrowserContext; panel: Page; target: Page; worker: Worker; id: string; activate: () => Promise<void> }
const test = base.extend<{ extension: Extension }>({
  extension: async ({ login: session }, use, testInfo) => {
    const profile = mkdtempSync(join(tmpdir(), 'resumate-extension-profile-'))
    const source = resolve(process.env.RESUMATE_EXTENSION_PATH || 'extension')
    const context = await chromium.launchPersistentContext(profile, {
      channel: 'chromium', headless: !process.env.RESUMATE_EXTENSION_HEADED,
      viewport: { width: 390, height: 900 },
      args: [`--disable-extensions-except=${source}`, `--load-extension=${source}`],
    })
    let panel: Page | undefined
    try {
      const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker')
      const id = new URL(worker.url()).host
      const target = context.pages()[0] || await context.newPage()
      await target.goto(`${SITE}/job-detail.html?case=${randomUUID()}&source=${'long-visible-source-'.repeat(12)}`)
      // Reuse a real Auth-issued token to avoid consuming the production 5/min login quota
      // for every isolated browser profile. The capture case still exercises UI login.
      await worker.evaluate(async ({ apiBase, token, username }) => {
        await (globalThis as any).chrome.storage.local.set({
          resumate_api_base: apiBase, resumate_auth_token: token, resumate_username: username,
        })
      }, { apiBase: API, token: session.access_token, username: session.username })
      panel = await context.newPage()
      await panel.goto(`chrome-extension://${id}/sidepanel/sidepanel.html`)
      await panel.locator('#languageZhBtn').click()
      // Keep the tab identity across navigation: Chrome hides chrome:// URLs from
      // extension tab queries, so locating a restricted page by URL is invalid.
      const targetTabId = await worker.evaluate(async url => {
        const tabs = await (globalThis as any).chrome.tabs.query({})
        const tab = tabs.find((item: any) => item.url === url)
        if (!tab) throw new Error('Target fixture tab is missing')
        return tab.id
      }, target.url())
      const activate = async () => {
        await worker.evaluate(async tabId => {
          await (globalThis as any).chrome.tabs.update(tabId, { active: true })
        }, targetTabId)
      }
      await use({ context, panel, target, worker, id, activate })
    } finally {
      if (panel && !panel.isClosed() && testInfo.status !== testInfo.expectedStatus) {
        writeFileSync(testInfo.outputPath('extension-failure.txt'), await panel.locator('body').innerText() + '\nDIAGNOSTICS\n' + await panel.locator('#debugOutput').textContent())
        await panel.screenshot({ path: testInfo.outputPath('extension-failure.png'), fullPage: true })
      }
      await context.close()
      rmSync(profile, { recursive: true, force: true })
    }
  },
})

async function login(panel: Page, forceUi = false) {
  await expect(panel.locator('#authStatus')).toContainText('browser-fixture')
  if (!forceUi) {
    await panel.locator('#refreshProfilesBtn').click()
    await expect(panel.locator('#profileSelect option')).not.toHaveCount(0)
    await panel.locator('.settings-card').evaluate((node: HTMLDetailsElement) => { node.open = false })
    return
  }
  await panel.locator('.settings-card').evaluate((node: HTMLDetailsElement) => { node.open = true })
  await panel.locator('#logoutBtn').click()
  await panel.locator('#apiBaseInput').fill(API)
  await panel.locator('#usernameInput').fill('browser-fixture')
  await panel.locator('#passwordInput').fill('synthetic-browser-password')
  await panel.locator('#loginBtn').click()
  await expect(panel.locator('#authStatus')).toContainText('browser-fixture')
  await expect(panel.locator('#profileSelect option')).not.toHaveCount(0)
  await panel.locator('.settings-card').evaluate((node: HTMLDetailsElement) => { node.open = false })
}
async function shot(page: Page, name: string, width = 390) {
  await page.setViewportSize({ width, height: 900 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
}
async function confirmedVersion(api: APIRequestContext) {
  const runId = await createRun(api)
  const run = await snapshot(api, runId)
  const answer = await api.post(`/api/agent/runs/${runId}/actions/${run.actions[0]!.actionId}`, {
    data: { decision: 'submit', answers: { answer: '负责 API 和数据库设计。' }, expectedRevision: 1 },
  })
  expect(answer.status()).toBe(202)
  const id = (await waitForRun(api, runId, 'succeeded')).outputRefs[0]!.id
  const version = await (await api.get(`/api/resume-versions/${id}`)).json()
  const saved = await api.patch(`/api/resume-versions/${id}`, { data: {
    expectedRevision: 1,
    changes: version.structuredContent.changes.map((change: { id: string; section: string }) => ({
      id: change.id, status: change.section.startsWith('/work_experience') ? 'edited' : 'rejected',
      ...(change.section.startsWith('/work_experience') ? { editedText: frozenWork } : {}),
    })),
  } })
  expect(saved.status(), await saved.text()).toBe(200)
  const confirmed = await api.post(`/api/resume-versions/${id}/confirm`, { data: { expectedRevision: 2 } })
  expect(confirmed.status()).toBe(200)
  return confirmed.json()
}

test('真实扩展采集可见岗位、预览后收藏，正文变化重采集仍保留原岗位', async ({ extension, api }) => {
  const { panel, target, activate } = extension
  await login(panel, true)
  await expect(panel.locator('#captureJobBtn')).toBeVisible()
  await activate()
  await panel.locator('#captureJobBtn').click()
  await expect(panel.locator('#jobTextInput')).toHaveValue(/负责 Python API 与数据库设计/)
  const captured = await panel.locator('#jobTextInput').inputValue()
  for (const hidden of ['隐藏岗位机密标记', '不可见文字标记', '导航排除标记', '页脚排除标记', '表单输入排除标记', '文本域草稿排除标记', '脚本内容排除标记']) expect(captured).not.toContain(hidden)
  await expect(panel.locator('#jobUrlInput')).toHaveValue(target.url())
  await panel.locator('#jobTitleInput').fill('扩展收藏 · 平台后端工程师')
  await panel.locator('#jobCompanyInput').fill('示例团队')
  await shot(panel, 'extension-page-capture-preview-390')
  await shot(panel, 'extension-page-capture-preview-320', 320)
  await panel.locator('#saveJobBtn').click()
  await expect(panel.locator('#jobCaptureStatus')).toContainText('已收藏')
  let jobs = await (await api.get('/api/jobs?limit=100')).json()
  const saved = jobs.items.filter((job: any) => job.sourceUrl === target.url())
  expect(saved).toHaveLength(1)
  await api.patch(`/api/jobs/${saved[0].id}`, { data: { title: '本人已整理的岗位名称' } })
  await target.locator('#changingText').evaluate(node => { node.textContent = '新增岗位正文说明，不应创建第二个同来源岗位。' })
  await activate(); await panel.locator('#captureJobBtn').click()
  await expect(panel.locator('#jobTextInput')).toHaveValue(/新增岗位正文说明/)
  await panel.locator('#saveJobBtn').click()
  await expect(panel.locator('#jobCaptureStatus')).toContainText('该来源已收藏')
  jobs = await (await api.get('/api/jobs?limit=100')).json()
  expect(jobs.items.filter((job: any) => job.sourceUrl === target.url())).toHaveLength(1)
  const detail = await (await api.get(`/api/jobs/${saved[0].id}`)).json()
  expect(detail.title).toBe('本人已整理的岗位名称')
  expect(detail.text).toBe(captured)
  expect(detail.parseStatus).toBe('pending')
  expect(detail.primaryResumeId).toBe(1)
  await shot(panel, 'extension-page-capture-existing-390')
  writeFileSync(test.info().outputPath('capture-evidence.json'), JSON.stringify({ jobId: detail.id, sourceUrl: detail.sourceUrl, count: 1, title: detail.title, parseStatus: detail.parseStatus }, null, 2))
})

test('真实确认版本填入勾选字段，换版本失效旧扫描，退出后离线不回落旧档案', async ({ extension, api }) => {
  const original = await (await api.get('/api/documents/resume:1')).json()
  const applications = await (await api.get('/api/applications')).json()
  const version = await confirmedVersion(api)
  const { panel, target, activate } = extension
  await login(panel)
  await panel.locator('#profileSelect').selectOption(`version:${version.id}`)
  await expect(panel.locator('#profileSelect option:checked')).toContainText('已确认版本')
  await expect(panel.locator('#profileFields')).toContainText(frozenWork)
  await target.goto(`${SITE}/application-form.html`)
  await activate(); await panel.locator('#scanBtn').click()
  await expect(panel.locator('#fillBtn')).toBeEnabled()
  await panel.locator('#profileSelect').selectOption('resume:1')
  await expect(panel.locator('#fillBtn')).toBeDisabled()
  await panel.locator('#profileSelect').selectOption(`version:${version.id}`)
  await expect(panel.locator('#profileFields')).toContainText(frozenWork)
  await activate(); await panel.locator('#scanBtn').click()
  await expect(panel.locator('#fillBtn')).toBeEnabled()
  const name = panel.locator('#matches label.match').filter({ hasText: '姓名' })
  await name.locator('input[type=checkbox]').uncheck()
  await shot(panel, 'extension-page-confirmed-preview-390')
  await shot(panel, 'extension-page-confirmed-preview-320', 320)
  await activate(); await panel.locator('#fillBtn').click()
  await expect(target.locator('[name=work_description]')).toHaveValue(frozenWork)
  await expect(target.locator('[name=candidate_name]')).toHaveValue('')
  await expect(target.locator('[name=captcha]')).toHaveValue('')
  expect(await target.evaluate(() => [(window as any).fixtureSubmissions, (window as any).fixtureSubmitClicks])).toEqual([0, 0])
  expect((await (await api.get('/api/documents/resume:1')).json()).parsed_content).toEqual(original.parsed_content)
  expect(await (await api.get('/api/applications')).json()).toEqual(applications)
  await shot(panel, 'extension-page-filled-390')
  await shot(target, 'extension-target-filled-unsubmitted', 1000)
  writeFileSync(test.info().outputPath('version-fill-evidence.json'), JSON.stringify({ versionId: version.id, revision: version.revision, text: frozenWork, submissionCount: 0, submitClicks: 0, mainResumeUnchanged: true, applicationsUnchanged: true }, null, 2))
  await panel.locator('.settings-card').evaluate((node: HTMLDetailsElement) => { node.open = true })
  await panel.locator('#logoutBtn').click()
  await expect(panel.locator('#profileSelect option')).toHaveCount(0)
  await extension.context.setOffline(true)
  await panel.locator('#refreshProfilesBtn').click()
  await expect(panel.locator('#profileSelect option')).toHaveCount(0)
  await expect(panel.locator('#profileFields')).not.toContainText(frozenWork)
  await extension.context.setOffline(false)
})

test('受限页面可粘贴收藏，空输入显示提示并保持米棕侧栏布局', async ({ extension, api }) => {
  const { panel, target, activate } = extension
  await login(panel)
  await target.goto('chrome://version/')
  await activate(); await panel.locator('#captureJobBtn').click()
  await expect(panel.locator('#jobCaptureStatus')).toContainText(/粘贴/)
  await panel.locator('#jobTitleInput').fill('')
  await panel.locator('#jobTextInput').fill('')
  await panel.locator('#saveJobBtn').click()
  await expect(panel.locator('#jobCaptureStatus')).toContainText(/标题|正文/)
  await shot(panel, 'extension-page-restricted-empty-320', 320)
  const title = `受限页粘贴-${randomUUID()}`
  await panel.locator('#jobTitleInput').fill(title)
  await panel.locator('#jobUrlInput').fill('')
  await panel.locator('#jobTextInput').fill('通过本人粘贴保存的合成岗位，负责接口设计与测试。')
  await panel.locator('#saveJobBtn').click()
  await expect(panel.locator('#jobCaptureStatus')).toContainText('已收藏')
  const jobs = await (await api.get('/api/jobs?limit=100')).json()
  expect(jobs.items.some((job: any) => job.title === title && job.sourceUrl === null)).toBe(true)
  await shot(panel, 'extension-page-paste-saved-390')
})

test('主应用插件下载说明展示收藏和确认版本，桌面手机布局一致', async ({ page, api }) => {
  void api
  await page.goto('/extension')
  await expect(page.getByText('收藏当前岗位', { exact: true })).toBeVisible()
  await expect(page.getByText('选择简历版本', { exact: true })).toBeVisible()
  await shot(page, 'extension-guide-desktop', 1440)
  await shot(page, 'extension-guide-mobile', 390)
  expect(await page.locator('.extension-workflow small').evaluateAll(nodes => nodes.every(node => node.scrollWidth <= node.clientWidth))).toBe(true)
})
