import { test as base, expect, type APIRequestContext } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export interface RunSnapshot {
  runId: string
  status: string
  cancelRequested: boolean
  lastSeq: number
  errorCode: string | null
  outputRefs: Array<{ type: string; id: string }>
  actions: Array<{ actionId: string; revision: number; payload: { question: string } }>
}

interface Login { access_token: string; username: string; role: string }
export const test = base.extend<{ api: APIRequestContext }, { login: Login }>({
  login: [async ({ playwright }, use) => {
    const auth = await playwright.request.newContext({ baseURL: 'http://127.0.0.1:4174' })
    const response = await auth.post('/auth/login', {
      data: { username: 'browser-fixture', password: 'synthetic-browser-password' },
    })
    expect(response.status(), await response.text()).toBe(200)
    await use(await response.json())
    await auth.dispose()
  }, { scope: 'worker' }],
  api: async ({ playwright, context, login }, use) => {
    await context.addInitScript(({ access_token, username, role }) => {
      localStorage.setItem('accessToken', access_token)
      localStorage.setItem('username', username)
      localStorage.setItem('role', role)
    }, login)
    const api = await playwright.request.newContext({
      baseURL: 'http://127.0.0.1:4174',
      extraHTTPHeaders: { Authorization: `Bearer ${login.access_token}` },
    })
    await use(api)
    await api.dispose()
  },
})

export { expect }

export function seededPausedRun(): string {
  return JSON.parse(readFileSync(join(process.env.RESUMATE_E2E_ROOT!, 'fixture.json'), 'utf8')).pausedRunId
}

export async function snapshot(api: APIRequestContext, runId: string): Promise<RunSnapshot> {
  const response = await api.get(`/api/agent/runs/${runId}`)
  expect(response.ok()).toBeTruthy()
  return response.json()
}

export async function waitForRun(api: APIRequestContext, runId: string, status: string) {
  await expect.poll(async () => (await snapshot(api, runId)).status, {
    message: `Run ${runId} reaches ${status} through the real worker`,
    timeout: 25_000,
  }).toBe(status)
  return snapshot(api, runId)
}

export async function createRun(api: APIRequestContext, waitStatus = 'waiting_input') {
  const response = await api.post('/api/agent/runs', {
    data: { kind: 'tailoring', jdId: 1, resumeId: 1, requestId: randomUUID() },
  })
  expect(response.status()).toBe(202)
  const { runId } = await response.json()
  await waitForRun(api, runId, waitStatus)
  return runId as string
}
