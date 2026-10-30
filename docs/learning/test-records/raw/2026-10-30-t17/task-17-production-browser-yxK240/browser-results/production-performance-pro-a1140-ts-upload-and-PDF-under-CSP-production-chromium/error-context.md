# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: production-performance.spec.ts >> production lazy routes, local input frames, long layouts, upload and PDF under CSP
- Location: tests/e2e/production-performance.spec.ts:65:1

# Error details

```
Error: Run 0f2d7e9f-4a4f-4c8c-ad36-37adbeaf6727 reaches succeeded through the real worker

Run 0f2d7e9f-4a4f-4c8c-ad36-37adbeaf6727 reaches succeeded through the real worker

expect(received).toBe(expected) // Object.is equality

Expected: "succeeded"
Received: "failed"

Call Log:
- Timeout 25000ms exceeded while waiting on the predicate
```

# Page snapshot

```yaml
- generic [ref=f1e3]:
  - complementary "主导航" [ref=f1e4]:
    - link "ResuMate 首页" [ref=f1e5] [cursor=pointer]:
      - /url: /
      - generic [ref=f1e10]:
        - strong [ref=f1e11]: ResuMate.
        - generic [ref=f1e12]: 你的招聘好伙伴
    - navigation [ref=f1e13]:
      - link "岗位中心" [ref=f1e14] [cursor=pointer]:
        - /url: /jobs
      - link "文档管理" [active] [ref=f1e21] [cursor=pointer]:
        - /url: /documents
      - link "岗位匹配" [ref=f1e28] [cursor=pointer]:
        - /url: /matching
      - link "材料准备" [ref=f1e38] [cursor=pointer]:
        - /url: /agent/tasks
      - link "结构资料" [ref=f1e44] [cursor=pointer]:
        - /url: /profile-fields
      - link "试题生成" [ref=f1e50] [cursor=pointer]:
        - /url: /questions
      - link "投递记录" [ref=f1e56] [cursor=pointer]:
        - /url: /applications
      - link "浏览器插件" [ref=f1e61] [cursor=pointer]:
        - /url: /extension
      - link "设置" [ref=f1e66] [cursor=pointer]:
        - /url: /settings
    - region "米洛的工作状态" [ref=f1e72]:
      - status [ref=f1e73]:
        - text: 米洛
        - paragraph [ref=f1e74]: 我准备好啦，等你开始分析。
      - img "米洛" [ref=f1e75]
    - generic [ref=f1e76]:
      - generic [aria-hidden] [ref=f1e77]: B
      - generic [ref=f1e78]:
        - strong [ref=f1e79]: browser-fixture
        - generic [ref=f1e80]: 我的账号
      - button "退出登录" [ref=f1e81] [cursor=pointer]
  - main [ref=f1e86]:
    - generic [ref=f1e87]:
      - generic [ref=f1e88]:
        - heading "文档管理" [level=1] [ref=f1e89]
        - paragraph [ref=f1e90]: 上传、解析、查看和删除 JD 与简历
      - generic [ref=f1e91]:
        - generic [ref=f1e92]: browser-deterministic
        - generic [ref=f1e93] [cursor=pointer]:
          - generic [ref=f1e94]: 玻璃效果
          - switch "玻璃效果" [ref=f1e95]
    - generic [ref=f1e98]:
      - generic [ref=f1e99]:
        - article [ref=f1e100]:
          - text: JD 数量
          - strong [ref=f1e101]: "1"
        - article [ref=f1e102]:
          - text: 简历数量
          - strong [ref=f1e103]: "1"
        - article [ref=f1e104]:
          - text: 已解析
          - strong [ref=f1e105]: "2"
        - article [ref=f1e106]:
          - text: 处理中
          - strong [ref=f1e107]: "0"
      - generic [ref=f1e108]:
        - generic [ref=f1e110]:
          - heading "上传文档" [level=2] [ref=f1e111]
          - paragraph [ref=f1e112]: 上传后自动开始解析，你可以在下方查看处理进度和结果。
          - paragraph [ref=f1e113]: 离开此页会停止队列中尚未开始上传的文件；已受理任务会继续，可以回来查看进度。
        - generic [ref=f1e115]:
          - generic [ref=f1e116]:
            - generic [ref=f1e117] [cursor=pointer]:
              - button "上传 JD 文件" [ref=f1e118]
              - strong [ref=f1e122]: 上传 JD
              - generic [ref=f1e123]: 支持 PDF、DOC、DOCX、TXT、MD
            - button "输入 JD 文本" [ref=f1e124] [cursor=pointer]
          - generic [ref=f1e127]:
            - generic [ref=f1e128] [cursor=pointer]:
              - button "上传简历文件" [ref=f1e129]
              - strong [ref=f1e135]: 上传简历
              - generic [ref=f1e136]: 可一次选择多份简历文件
            - button "输入简历文本" [ref=f1e137] [cursor=pointer]
      - generic [ref=f1e140]:
        - generic [ref=f1e142]:
          - heading "文档解析进度" [level=2] [ref=f1e143]
          - paragraph [ref=f1e144]: 1 个任务
        - article [ref=f1e146]:
          - generic [ref=f1e147]:
            - generic [ref=f1e148]:
              - strong [ref=f1e149]: 生产代理上传验证.txt
              - generic [ref=f1e150]: 解析失败
            - generic [ref=f1e151]:
              - strong [ref=f1e152]: 100%
              - generic [ref=f1e153]: 失败
          - generic "文档解析总体进度" [ref=f1e154]:
            - generic "文件上传 · 100%" [ref=f1e155]
            - generic "文本提取 · 100%" [ref=f1e157]
            - generic "Agent 分析 · 100%" [ref=f1e159]
            - generic "向量化入库 · 0%" [ref=f1e161]
          - generic [ref=f1e162]:
            - generic "Uploading 100%" [ref=f1e163]:
              - generic [ref=f1e167]:
                - strong [ref=f1e168]: 文件上传
                - generic [ref=f1e169]: 已完成
            - generic "正在提取第 1/1 页" [ref=f1e170]:
              - generic [ref=f1e174]:
                - strong [ref=f1e175]: 文本提取
                - generic [ref=f1e176]: 已完成
            - generic "document_parse_failed" [ref=f1e177]:
              - generic [ref=f1e181]:
                - strong [ref=f1e182]: Agent 分析
                - generic [ref=f1e183]: 失败
            - generic "向量化入库" [ref=f1e184]:
              - generic [ref=f1e187]:
                - strong [ref=f1e188]: 向量化入库
                - generic [ref=f1e189]: 等待中
          - paragraph [ref=f1e190]: document_parse_failed
          - link "查看任务与结果" [ref=f1e191] [cursor=pointer]:
            - /url: /agent/tasks/0f2d7e9f-4a4f-4c8c-ad36-37adbeaf6727
          - paragraph [ref=f1e192]: 失败原因：document_parse_failed
      - generic [ref=f1e193]:
        - generic [ref=f1e194]:
          - heading "文档列表" [level=2] [ref=f1e195]
          - button "刷新" [ref=f1e196] [cursor=pointer]
        - generic [ref=f1e197]:
          - button "全部文档" [ref=f1e198] [cursor=pointer]
          - button "JD" [ref=f1e199] [cursor=pointer]
          - button "简历" [ref=f1e200] [cursor=pointer]
        - generic [ref=f1e201]:
          - generic [ref=f1e202]:
            - generic [ref=f1e203]: 类型
            - combobox "类型" [ref=f1e204]:
              - option "全部" [selected]
              - option "JD"
              - option "简历"
          - generic [ref=f1e205]:
            - generic [ref=f1e206]: 状态
            - combobox "状态" [ref=f1e207]:
              - option "全部" [selected]
              - option "未解析"
              - option "解析中"
              - option "成功"
              - option "失败"
          - generic [ref=f1e208]:
            - generic [ref=f1e209]: 搜索
            - searchbox "搜索" [ref=f1e210]
        - table [ref=f1e212]:
          - rowgroup [ref=f1e213]:
            - row [ref=f1e214]:
              - columnheader "文件名" [ref=f1e215]
              - columnheader "类型" [ref=f1e216]
              - columnheader "大小" [ref=f1e217]
              - columnheader "上传时间" [ref=f1e218]
              - columnheader "解析状态" [ref=f1e219]
              - columnheader "向量库" [ref=f1e220]
              - columnheader "本地保存" [ref=f1e221]
              - columnheader "操作" [ref=f1e222]
          - rowgroup [ref=f1e223]:
            - row [ref=f1e224]:
              - cell [ref=f1e225]:
                - button "E2E 主简历.txt" [ref=f1e226] [cursor=pointer]
              - cell "简历" [ref=f1e227]
              - cell "0 B" [ref=f1e228]
              - cell "10/30 10:44" [ref=f1e229]
              - cell "已完成" [ref=f1e230]
              - cell "已入库" [ref=f1e232]
              - cell "未保存" [ref=f1e234]
              - cell [ref=f1e236]:
                - generic [ref=f1e237]:
                  - button "查看" [ref=f1e238] [cursor=pointer]
                  - button "重解析" [ref=f1e243] [cursor=pointer]
                  - button "删除" [ref=f1e250] [cursor=pointer]
            - row [ref=f1e255]:
              - cell [ref=f1e256]:
                - button "E2E API 工程师" [ref=f1e257] [cursor=pointer]
              - cell "JD" [ref=f1e258]
              - cell "0 B" [ref=f1e259]
              - cell "10/30 10:44" [ref=f1e260]
              - cell "已完成" [ref=f1e261]
              - cell "未入库" [ref=f1e263]
              - cell "未保存" [ref=f1e265]
              - cell [ref=f1e267]:
                - generic [ref=f1e268]:
                  - button "查看" [ref=f1e269] [cursor=pointer]
                  - button "重解析" [ref=f1e274] [cursor=pointer]
                  - button "删除" [ref=f1e281] [cursor=pointer]
```

# Test source

```ts
  1  | import { test as base, expect, type APIRequestContext } from '@playwright/test'
  2  | import { randomUUID } from 'node:crypto'
  3  | import { execFileSync } from 'node:child_process'
  4  | import { readFileSync } from 'node:fs'
  5  | import { join } from 'node:path'
  6  | 
  7  | export interface RunSnapshot {
  8  |   runId: string
  9  |   status: string
  10 |   cancelRequested: boolean
  11 |   lastSeq: number
  12 |   errorCode: string | null
  13 |   outputRefs: Array<{ type: string; id: string }>
  14 |   actions: Array<{ actionId: string; revision: number; payload: { question: string } }>
  15 | }
  16 | 
  17 | const apiURL = `http://127.0.0.1:${process.env.RESUMATE_E2E_API_PORT || '4174'}`
  18 | 
  19 | interface Login { access_token: string; username: string; role: string }
  20 | export const test = base.extend<{ api: APIRequestContext; resetAdmission: void }, { login: Login }>({
  21 |   resetAdmission: [async ({ login: _login }, use) => {
  22 |     // Isolate each browser scenario's quota while retaining the actual Redis
  23 |     // limiter. Only this fixture user's run counter is reset, never queue data.
  24 |     execFileSync('.venv/bin/python', ['-c', [
  25 |       'import json, sys, redis',
  26 |       'fixture = json.load(open(sys.argv[1]))',
  27 |       "with redis.Redis.from_url(fixture['redisUrl']) as client:",
  28 |       "    client.delete(fixture['redisNamespace'] + ':rl:run:1')",
  29 |     ].join('\n'), join(process.env.RESUMATE_E2E_ROOT!, 'fixture.json')], { timeout: 10_000 })
  30 |     await use()
  31 |   }, { auto: true }],
  32 |   login: [async ({ playwright }, use) => {
  33 |     const auth = await playwright.request.newContext({ baseURL: apiURL })
  34 |     const response = await auth.post('/auth/login', {
  35 |       data: { username: 'browser-fixture', password: 'synthetic-browser-password' },
  36 |     })
  37 |     expect(response.status(), await response.text()).toBe(200)
  38 |     await use(await response.json())
  39 |     await auth.dispose()
  40 |   }, { scope: 'worker' }],
  41 |   api: async ({ playwright, context, login }, use) => {
  42 |     await context.addInitScript(({ access_token, username, role }) => {
  43 |       localStorage.setItem('accessToken', access_token)
  44 |       localStorage.setItem('username', username)
  45 |       localStorage.setItem('role', role)
  46 |     }, login)
  47 |     const api = await playwright.request.newContext({
  48 |       baseURL: apiURL,
  49 |       extraHTTPHeaders: { Authorization: `Bearer ${login.access_token}` },
  50 |     })
  51 |     await use(api)
  52 |     await api.dispose()
  53 |   },
  54 | })
  55 | 
  56 | export { expect }
  57 | 
  58 | export function seededPausedRun(): string {
  59 |   return JSON.parse(readFileSync(join(process.env.RESUMATE_E2E_ROOT!, 'fixture.json'), 'utf8')).pausedRunId
  60 | }
  61 | 
  62 | export async function snapshot(api: APIRequestContext, runId: string): Promise<RunSnapshot> {
  63 |   const response = await api.get(`/api/agent/runs/${runId}`)
  64 |   expect(response.ok()).toBeTruthy()
  65 |   return response.json()
  66 | }
  67 | 
  68 | export async function waitForRun(api: APIRequestContext, runId: string, status: string) {
  69 |   await expect.poll(async () => (await snapshot(api, runId)).status, {
  70 |     message: `Run ${runId} reaches ${status} through the real worker`,
  71 |     timeout: 25_000,
> 72 |   }).toBe(status)
     |      ^ Error: Run 0f2d7e9f-4a4f-4c8c-ad36-37adbeaf6727 reaches succeeded through the real worker
  73 |   return snapshot(api, runId)
  74 | }
  75 | 
  76 | export async function createRun(api: APIRequestContext, waitStatus = 'waiting_input') {
  77 |   const response = await api.post('/api/agent/runs', {
  78 |     data: { kind: 'tailoring', jdId: 1, resumeId: 1, requestId: randomUUID() },
  79 |   })
  80 |   expect(response.status()).toBe(202)
  81 |   const { runId } = await response.json()
  82 |   await waitForRun(api, runId, waitStatus)
  83 |   return runId as string
  84 | }
  85 | 
```