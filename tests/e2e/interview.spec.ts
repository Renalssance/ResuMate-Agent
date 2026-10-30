import { test, expect, createRun, snapshot, waitForRun } from './support/fixtures'
import type { APIRequestContext, Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import type { InterviewSnapshot } from '../../frontend/src/types/interview'

const marker = (name: string) => join(process.env.RESUMATE_E2E_ROOT!, `interview-${name}`)
async function read(api: APIRequestContext, id: string): Promise<InterviewSnapshot> {
  const response = await api.get(`/api/interviews/${id}`)
  expect(response.status(), await response.text()).toBe(200)
  return response.json()
}
async function ready(api: APIRequestContext, id: string, turn: number) {
  await expect.poll(async () => {
    const current = await read(api, id)
    return [current.currentTurn, current.generation?.status]
  }, { timeout: 25_000 }).toEqual([turn, 'succeeded'])
  return read(api, id)
}
async function application(api: APIRequestContext, suffix: string) {
  const runId = await createRun(api)
  const run = await snapshot(api, runId)
  expect((await api.post(`/api/agent/runs/${runId}/actions/${run.actions[0]!.actionId}`, { data: {
    decision: 'submit', answers: { answer: '负责 API 设计、数据库模型与接口联调。' }, expectedRevision: 1,
  } })).status()).toBe(202)
  const done = await waitForRun(api, runId, 'succeeded')
  const id = done.outputRefs[0]!.id
  const version = await (await api.get(`/api/resume-versions/${id}`)).json()
  expect((await api.patch(`/api/resume-versions/${id}`, { data: { expectedRevision: 1,
    changes: version.structuredContent.changes.map((item: { id: string; requires_input: boolean }) => ({
      id: item.id, status: item.requires_input ? 'rejected' : 'accepted',
    })),
  } })).status()).toBe(200)
  expect((await api.post(`/api/resume-versions/${id}/confirm`, { data: { expectedRevision: 2 } })).status()).toBe(200)
  const created = await api.post('/api/applications', { data: {
    company: `T16 ${suffix} · 示例科技有限公司`, position: '全栈开发工程师', applied_date: '2026-10-30', status: 'applied', jd_id: 1, resume_version_id: id,
  } })
  expect(created.status()).toBe(200)
  return created.json()
}
async function start(page: Page, applicationId: number, company: string) {
  await page.goto('/applications')
  const record = page.locator('.application-company-group').filter({ hasText: company })
  const response = page.waitForResponse(item => item.url().endsWith('/api/interviews') && item.request().method() === 'POST')
  await record.getByRole('button', { name: '模拟面试', exact: true }).click()
  const result = await response
  expect(result.status(), await result.text()).toBe(202)
  expect(result.request().postDataJSON().applicationId).toBe(applicationId)
  const { interviewId } = await result.json()
  await expect(page).toHaveURL(`/interviews/${interviewId}`)
  return interviewId as string
}
async function answer(page: Page, text: string) {
  await page.getByLabel('你的回答', { exact: true }).fill(text)
  await page.getByRole('button', { name: '提交回答', exact: true }).click()
}
async function capture(page: Page, name: string, width = 1440) {
  await page.setViewportSize({ width, height: width < 700 ? 844 : 1100 })
  if (width < 700) {
    const toggle = page.getByRole('button', { name: '打开导航', exact: true })
    if (await toggle.getAttribute('aria-expanded') === 'true') await page.getByRole('button', { name: '关闭导航', exact: true }).click()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
}
function sqlEvidence(interviewId: string, file: string) {
  const output = execFileSync('.venv/bin/python', ['-c', [
    'import json, sqlite3, sys',
    'db = sqlite3.connect(sys.argv[1]); db.row_factory = sqlite3.Row',
    "tables = ['interview_sessions','interview_turns','interview_commands','interview_events']",
    "result = {name: [dict(row) for row in db.execute('SELECT * FROM '+name+' WHERE '+('id' if name == 'interview_sessions' else 'interview_id')+'=?', (sys.argv[2],))] for name in tables}",
    'print(json.dumps(result, ensure_ascii=False))',
  ].join('\n'), join(process.env.RESUMATE_E2E_ROOT!, 'resumate.db'), interviewId], { encoding: 'utf8', timeout: 10_000 })
  writeFileSync(test.info().outputPath(file), output)
  return JSON.parse(output)
}

test('从固定投递材料开始、两次追问与刷新恢复，确认结束保留问答', async ({ page, api }) => {
  const selected = await application(api, '多轮练习')
  writeFileSync(marker('long'), '')
  try {
    const id = await start(page, selected.id, selected.company)
    const first = await ready(api, id, 1)
    expect(first.sourceSnapshot.resumeVersionId).toBe(selected.resume_version_id)
    await expect(page.getByLabel('你的回答', { exact: true })).toBeVisible()
    await capture(page, 'interview-question-desktop')
    await answer(page, '我用一个数据库事务保存回答和任务，并以唯一键处理重复请求。')
    await ready(api, id, 2)
    await expect(page.getByLabel('你的回答', { exact: true })).toBeVisible()
    await answer(page, '遇到并发冲突先回滚，再读取原命令的确认结果，不再次创建任务。')
    const third = await ready(api, id, 3)
    expect(third.turns.filter(turn => turn.questionContext?.mode === 'follow_up')).toHaveLength(2)
    await page.reload()
    await expect(page.locator('.interview-current')).toContainText('第 3 题')
    await page.locator('.interview-current summary').click()
    await capture(page, 'interview-feedback-desktop')
    await capture(page, 'interview-long-390', 390)
    await capture(page, 'interview-long-320', 320)
    await page.getByRole('button', { name: '结束练习', exact: true }).click()
    await page.getByRole('button', { name: '确认结束练习', exact: true }).click()
    await expect(page.getByRole('heading', { name: '本次练习已结束', exact: true })).toBeVisible()
    expect((await read(api, id)).turns.filter(turn => turn.answer !== null)).toHaveLength(2)
    await capture(page, 'interview-finished-390', 390)
    sqlEvidence(id, 'multi-round-sql.json')
  } finally { rmSync(marker('long'), { force: true }) }
})

test('生成中停止、迟到结果不出现，失败后只重试原轮生成', async ({ page, api }) => {
  const selected = await application(api, '停止与重试')
  writeFileSync(marker('pause'), '')
  let id = ''
  try {
    id = await start(page, selected.id, selected.company)
    await expect.poll(async () => (await read(api, id)).generation?.status).toBe('running')
    await capture(page, 'interview-generating-320', 320)
    await page.getByRole('button', { name: '停止生成', exact: true }).click()
    await expect(page.locator('.interview-progress')).toContainText('正在停止')
    await capture(page, 'interview-stopping-390', 390)
  } finally { rmSync(marker('pause'), { force: true }) }
  await expect.poll(async () => (await read(api, id)).generation?.status).toBe('cancelled')
  expect((await read(api, id)).turns).toHaveLength(0)
  await page.getByRole('button', { name: '重试生成', exact: true }).click()
  await ready(api, id, 1)
  await expect(page.getByLabel('你的回答', { exact: true })).toBeVisible()
  writeFileSync(marker('fail-once'), '')
  try {
    await answer(page, '先用唯一键约束请求，再用事务保证回答和任务同步。')
    await expect.poll(async () => (await read(api, id)).generation?.status).toBe('failed')
    await expect(page.getByRole('button', { name: '重试生成', exact: true })).toBeVisible()
    await capture(page, 'interview-failed-390', 390)
    const before = await read(api, id)
    expect(before.turns[0]!.answer).toContain('唯一键')
    await page.getByRole('button', { name: '重试生成', exact: true }).click()
    const after = await ready(api, id, 2)
    expect(after.turns.filter(turn => turn.answer !== null)).toHaveLength(1)
    sqlEvidence(id, 'cancel-retry-sql.json')
  } finally { rmSync(marker('fail-once'), { force: true }) }
})

test('丢弃真实成功响应后重发原命令，确认记忆后删除使旧练习失效', async ({ page, api }) => {
  const selected = await application(api, '重发与记忆')
  const id = await start(page, selected.id, selected.company)
  await ready(api, id, 1)
  await expect(page.getByLabel('你的回答', { exact: true })).toBeVisible()
  let dropped = false
  const commands: unknown[] = []
  await page.route(`**/api/interviews/${id}/commands`, async route => {
    const command = route.request().postDataJSON()
    if (command.type === 'answer.submit') {
      commands.push(command)
      if (!dropped) {
        dropped = true
        const result = await route.fetch()
        expect(result.status()).toBe(202)
        await route.abort('failed')
        return
      }
    }
    await route.continue()
  })
  await answer(page, '我用事务与命令唯一键保存，重复提交读取原确认结果。')
  await expect(page.getByRole('button', { name: '重新发送原回答', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '重新发送原回答', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重新发送原回答', exact: true }).click()
  await ready(api, id, 2)
  expect(commands).toHaveLength(2)
  expect(commands[1]).toEqual(commands[0])
  const evidence = sqlEvidence(id, 'lost-ack-sql.json')
  expect(evidence.interview_commands.filter((row: { type: string }) => row.type === 'answer.submit')).toHaveLength(1)
  expect(evidence.interview_turns.filter((row: { answer: string | null }) => row.answer !== null)).toHaveLength(1)
  const before = await (await api.get('/api/memories')).json()
  await page.getByRole('button', { name: '保存练习要点', exact: true }).click()
  await expect(page.getByRole('region', { name: '确认练习记忆' })).toBeVisible()
  expect((await (await api.get('/api/memories')).json()).items).toHaveLength(before.items.length)
  await capture(page, 'interview-memory-confirm-390', 390)
  await page.getByRole('button', { name: '确认保存记忆', exact: true }).click()
  await expect(page.getByText('已保存练习记忆', { exact: true })).toBeVisible()
  const saved = await read(api, id)
  const memoryId = saved.turns[0]!.feedback!.memoryId!
  writeFileSync(marker('pause'), '')
  try {
    await answer(page, '我会补充并发执行下的冲突处理过程。')
    await expect.poll(async () => (await read(api, id)).generation?.status).toBe('running')
    expect((await api.delete(`/api/memories/${memoryId}`)).ok()).toBeTruthy()
    await expect(page.locator('.interview-page')).toContainText('这次练习使用的记忆已删除')
    await expect(page.locator('.interview-current')).not.toContainText('正在整理反馈与下一题')
    await capture(page, 'interview-memory-invalidated-390', 390)
  } finally { rmSync(marker('pause'), { force: true }); await api.delete(`/api/memories/${memoryId}`) }
  await page.unroute(`**/api/interviews/${id}/commands`)
})

test('缺失会话显示返回入口，源材料变化不替换已经冻结的练习', async ({ page, api }) => {
  await page.goto(`/interviews/${randomUUID()}`)
  await expect(page.getByRole('heading', { name: '暂时无法读取这次练习' })).toBeVisible()
  await capture(page, 'interview-empty-320', 320)
  const selected = await application(api, '冻结材料')
  const id = await start(page, selected.id, selected.company)
  const before = await ready(api, id, 1)
  const source = await (await api.get('/api/documents/resume:1')).json()
  try {
    expect((await api.patch('/api/documents/resume:1/structured-data', { data: { structured_data: { ...source.parsed_content, candidate_name: '后来修改的资料' } } })).ok()).toBeTruthy()
    await page.reload()
    await expect(page.getByLabel('你的回答', { exact: true })).toBeVisible()
    expect((await read(api, id)).sourceSnapshot).toEqual(before.sourceSnapshot)
    await expect(page.locator('.interview-page')).not.toContainText('后来修改的资料')
    sqlEvidence(id, 'frozen-source-sql.json')
  } finally { await api.patch('/api/documents/resume:1/structured-data', { data: { structured_data: source.parsed_content } }) }
})
