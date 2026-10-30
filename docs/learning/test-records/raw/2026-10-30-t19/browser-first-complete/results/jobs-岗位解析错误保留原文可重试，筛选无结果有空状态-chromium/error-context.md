# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: jobs.spec.ts >> 岗位解析错误保留原文可重试，筛选无结果有空状态
- Location: tests/e2e/jobs.spec.ts:103:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: "success"
Received: "failed"

Call Log:
- Timeout 15000ms exceeded while waiting on the predicate
```

# Page snapshot

```yaml
- main [ref=e4]:
  - generic [ref=e5]:
    - button "打开导航" [ref=e6] [cursor=pointer]
    - heading "岗位中心" [level=1] [ref=e9]
    - generic [ref=e10]:
      - generic [ref=e11]: browser-deterministic
      - generic [ref=e12] [cursor=pointer]:
        - generic [ref=e13]: 玻璃效果
        - switch "玻璃效果" [ref=e14]
  - generic [ref=e17]:
    - generic [ref=e18]:
      - generic [ref=e20]:
        - heading "收藏目标岗位" [level=2] [ref=e21]
        - paragraph [ref=e22]: 把岗位原文留在这里，关联主简历，再开始匹配和准备材料。
      - generic [ref=e23]:
        - generic [ref=e24]:
          - generic [ref=e25]:
            - generic [ref=e26]: 岗位名称
            - textbox "岗位名称" [ref=e27]:
              - /placeholder: 如：平台工程师
          - generic [ref=e28]:
            - generic [ref=e29]: 公司
            - textbox "公司" [ref=e30]:
              - /placeholder: 公司名称（选填）
          - generic [ref=e31]:
            - generic [ref=e32]: 来源链接
            - textbox "来源链接" [ref=e33]:
              - /placeholder: 粘贴招聘页面链接（选填）
        - generic [ref=e34]:
          - generic [ref=e35]: 岗位原文
          - textbox "岗位原文" [ref=e36]:
            - /placeholder: 粘贴岗位职责、任职要求等原文。收藏后可以解析岗位。
        - generic [ref=e37]:
          - button "收藏岗位" [disabled] [ref=e38]
          - generic [ref=e39]: 重复收藏会打开已有岗位。
    - generic [ref=e40]:
      - generic [ref=e41]:
        - generic [ref=e42]:
          - heading "我的岗位" [level=2] [ref=e43]
          - button "刷新" [ref=e44] [cursor=pointer]
        - generic [ref=e45]:
          - generic [ref=e46]:
            - generic [ref=e47]: 搜索岗位
            - searchbox "搜索岗位" [ref=e48]
          - generic [ref=e49]:
            - generic [ref=e50]: 岗位状态
            - combobox "岗位状态" [ref=e51]:
              - option "全部状态" [selected]
              - option "已收藏"
              - option "已归档"
          - button "搜索" [ref=e52] [cursor=pointer]
        - list [ref=e53]:
          - listitem [ref=e54]:
            - button "解析重试示例 未填写公司 已收藏 · 解析失败 10/30 12:00" [ref=e55]:
              - strong [ref=e56]: 解析重试示例
              - generic [ref=e57]: 未填写公司
              - generic [ref=e58]: 已收藏 · 解析失败
              - time [ref=e59]: 10/30 12:00
          - listitem [ref=e60]:
            - button "平台 API 工程师 示例科技团队 已收藏 · 已解析 10/30 12:00" [ref=e61]:
              - strong [ref=e62]: 平台 API 工程师
              - generic [ref=e63]: 示例科技团队
              - generic [ref=e64]: 已收藏 · 已解析
              - time [ref=e65]: 10/30 12:00
          - listitem [ref=e66]:
            - button "受限页粘贴-1735056a-2ed9-4e4c-9473-5ddd8030acd7 未填写公司 已收藏 · 待解析 10/30 11:59" [ref=e67]:
              - strong [ref=e68]: 受限页粘贴-1735056a-2ed9-4e4c-9473-5ddd8030acd7
              - generic [ref=e69]: 未填写公司
              - generic [ref=e70]: 已收藏 · 待解析
              - time [ref=e71]: 10/30 11:59
          - listitem [ref=e72]:
            - button "本人已整理的岗位名称 示例团队 已收藏 · 待解析 10/30 11:59" [ref=e73]:
              - strong [ref=e74]: 本人已整理的岗位名称
              - generic [ref=e75]: 示例团队
              - generic [ref=e76]: 已收藏 · 待解析
              - time [ref=e77]: 10/30 11:59
          - listitem [ref=e78]:
            - button "E2E API 工程师 示例团队 已收藏 · 已解析 10/30 11:58" [ref=e79]:
              - strong [ref=e80]: E2E API 工程师
              - generic [ref=e81]: 示例团队
              - generic [ref=e82]: 已收藏 · 已解析
              - time [ref=e83]: 10/30 11:58
        - generic [ref=e84]:
          - button "上一页" [disabled] [ref=e85]
          - generic [ref=e86]: 第 1 页
          - button "下一页" [disabled] [ref=e87]
      - region "岗位详情" [ref=e88]:
        - generic [ref=e90]:
          - heading "解析重试示例" [level=2] [ref=e91]
          - paragraph [ref=e92]: 未填写公司 · 解析失败
        - generic [ref=e93]:
          - generic [ref=e94]:
            - generic [ref=e95]: 编辑岗位名称
            - textbox "编辑岗位名称" [ref=e96]: 解析重试示例
          - generic [ref=e97]:
            - generic [ref=e98]: 编辑公司
            - textbox "编辑公司" [ref=e99]
          - generic [ref=e100]:
            - generic [ref=e101]: 收藏状态
            - combobox "收藏状态" [ref=e102]:
              - option "已收藏" [selected]
              - option "已归档"
          - generic [ref=e103]:
            - generic [ref=e104]: 主简历
            - combobox "主简历" [ref=e105]:
              - option "暂不关联" [selected]
              - option "示例求职者（E2E 主简历.txt）"
          - button "保存岗位" [ref=e106] [cursor=pointer]
        - button "重试解析" [ref=e108] [cursor=pointer]
        - paragraph [ref=e109]: 解析成功后可以匹配岗位和准备材料。
        - alert [ref=e110]: 岗位解析未完成。原文已保留，可以重试解析。
        - group [ref=e111]:
          - generic "查看错误详情" [ref=e112] [cursor=pointer]
        - generic [ref=e113]:
          - heading "岗位解析进度" [level=2] [ref=e116]
          - article [ref=e117]:
            - generic [ref=e118]:
              - strong [ref=e120]: 解析失败
              - strong [ref=e122]: 100%
            - generic "任务进度" [ref=e123]:
              - generic "读取岗位原文 · 100%" [ref=e124]
              - generic "分析岗位要求 · 100%" [ref=e126]
              - generic "保存解析结果 · 0%" [ref=e128]
            - generic [ref=e129]:
              - generic "读取岗位原文" [ref=e130]:
                - generic [ref=e134]:
                  - strong [ref=e135]: 读取岗位原文
                  - generic [ref=e136]: 已完成
              - 'generic "LLM analysis failed: InternalServerError" [ref=e137]':
                - generic [ref=e141]:
                  - strong [ref=e142]: 分析岗位要求
                  - generic [ref=e143]: 进行中 100%
              - generic "保存解析结果" [ref=e144]:
                - generic [ref=e147]:
                  - strong [ref=e148]: 保存解析结果
                  - generic [ref=e149]: 等待中
            - paragraph [ref=e150]: 岗位解析未完成，请稍后重试。
        - group [ref=e151]:
          - generic "岗位原文" [ref=e152] [cursor=pointer]
          - paragraph [ref=e153]: E2E_RETRY_PARSE 负责 API 和数据库设计。
        - generic [ref=e154]:
          - heading "历史匹配" [level=3] [ref=e155]
          - paragraph [ref=e156]: 尚未匹配这个岗位。解析后选择简历，开始第一次匹配。
          - list
```

# Test source

```ts
  14  |   await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  15  |   await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width)
  16  |   if (name.startsWith('facts-')) {
  17  |     await page.getByRole('region', { name: '确认事实', exact: true }).screenshot({ path: test.info().outputPath(`${name}.png`), animations: 'disabled' })
  18  |   } else {
  19  |     await page.screenshot({ path: test.info().outputPath(`${name}.png`), fullPage: mobile || fullPage, animations: 'disabled' })
  20  |   }
  21  | }
  22  | 
  23  | // Every business response below comes from the actual API and SQL. Only the
  24  | // external model HTTP transport is replaced in the test API entrypoint.
  25  | test('岗位收藏解析关联后进入材料准备并由独立 worker 完成', async ({ page, api }) => {
  26  |   await page.goto('/jobs')
  27  |   await page.getByLabel('岗位名称', { exact: true }).fill('平台 API 工程师')
  28  |   await page.getByLabel('公司', { exact: true }).fill('示例科技团队')
  29  |   await page.getByLabel('岗位原文', { exact: true }).fill(jobText)
  30  |   await page.getByLabel('来源链接', { exact: true }).fill('https://example.com/jobs/backend')
  31  |   const saved = page.waitForResponse(r => r.url().endsWith('/api/jobs') && r.request().method() === 'POST')
  32  |   await page.getByRole('button', { name: '收藏岗位', exact: true }).click()
  33  |   const response = await saved
  34  |   expect(response.ok()).toBe(true)
  35  |   const { job, created } = await response.json()
  36  |   expect(created).toBe(true)
  37  |   const detail = page.getByRole('region', { name: '岗位详情', exact: true })
  38  |   await expect(detail).toBeVisible()
  39  |   await capture(page, 'jobs-long-desktop', false, true)
  40  |   await capture(page, 'jobs-long-mobile', true)
  41  |   await page.setViewportSize({ width: 1440, height: 1100 })
  42  |   await detail.getByLabel('主简历', { exact: true }).selectOption('1')
  43  |   await detail.getByRole('button', { name: '保存岗位', exact: true }).click()
  44  |   await expect.poll(async () => (await (await api.get(`/api/jobs/${job.id}`)).json()).primaryResumeId).toBe(1)
  45  |   await detail.getByRole('button', { name: '解析岗位', exact: true }).click()
  46  |   await expect.poll(async () => (await (await api.get(`/api/jobs/${job.id}`)).json()).parseStatus).toBe('success')
  47  |   await detail.getByRole('link', { name: '去匹配', exact: true }).click()
  48  |   await expect(page).toHaveURL(/\/matching\?/)
  49  |   await expect(page.getByRole('combobox', { name: '目标 JD', exact: true })).toHaveValue(`jd:${job.id}`)
  50  |   await expect(page.getByRole('listbox', { name: '候选人简历', exact: true })).toHaveValues(['resume:1'])
  51  |   await page.goto('/jobs')
  52  |   await page.locator(`[data-job-id="${job.id}"]`).click()
  53  |   await page.getByRole('region', { name: '岗位详情', exact: true }).getByRole('link', { name: '准备材料', exact: true }).click()
  54  |   await expect(page.getByRole('combobox', { name: '目标岗位', exact: true })).toHaveValue(`jd:${job.id}`)
  55  |   await expect(page.getByRole('combobox', { name: '主简历', exact: true })).toHaveValue('resume:1')
  56  |   await page.getByRole('button', { name: '开始准备', exact: true }).click()
  57  |   await expect(page).toHaveURL(/\/agent\/tasks\/[^/?]+$/)
  58  |   const runId = page.url().split('/').pop()!
  59  |   await page.getByLabel('你负责什么工作？', { exact: true }).fill('负责 API 和数据库设计。')
  60  |   await page.getByRole('button', { name: '继续任务', exact: true }).click()
  61  |   await expect(page.getByRole('heading', { name: '材料已生成', exact: true })).toBeVisible()
  62  |   expect((await waitForRun(api, runId, 'succeeded')).outputRefs).toHaveLength(1)
  63  |   expect((await snapshot(api, runId)).cancelRequested).toBe(false)
  64  | })
  65  | 
  66  | test('用户确认经历后编辑保留历史，删除后可追溯', async ({ page, api }) => {
  67  |   await page.goto('/profile-fields')
  68  |   await page.getByRole('combobox', { name: '选择简历', exact: true }).selectOption('resume:1')
  69  |   const facts = page.getByRole('region', { name: '确认事实', exact: true })
  70  |   await expect(facts).toBeVisible()
  71  |   await facts.getByLabel('从简历选择经历', { exact: true }).selectOption('work_experience:0')
  72  |   await expect(facts.getByLabel('我已核对，确认这条事实', { exact: true })).not.toBeChecked()
  73  |   await facts.getByLabel('事实内容', { exact: true }).fill('负责 API 和数据库设计，并与团队核对接口需求。'.repeat(8))
  74  |   await facts.getByLabel('我已核对，确认这条事实', { exact: true }).check()
  75  |   const saved = page.waitForResponse(r => r.url().endsWith('/api/profile-facts') && r.request().method() === 'POST')
  76  |   await facts.getByRole('button', { name: '保存事实', exact: true }).click()
  77  |   const initial = await (await saved).json()
  78  |   expect(initial.revision).toBe(1)
  79  |   expect(initial.sourceDocumentId).toBe(1)
  80  |   expect(initial.confirmedAt).toBeTruthy()
  81  |   await capture(page, 'facts-confirmed-desktop')
  82  |   await capture(page, 'facts-confirmed-mobile', true)
  83  |   await facts.getByRole('button', { name: '编辑事实', exact: true }).first().click()
  84  |   await facts.getByLabel('事实内容', { exact: true }).fill('负责 API 设计、数据库模型与接口联调。')
  85  |   const updated = page.waitForResponse(r => r.url().includes('/api/profile-facts/') && r.request().method() === 'PATCH')
  86  |   await facts.getByRole('button', { name: '保存修改', exact: true }).click()
  87  |   const second = await (await updated).json()
  88  |   expect(second.revision).toBe(2)
  89  |   expect(second.confirmedAt).toBeNull()
  90  |   await facts.getByRole('button', { name: '查看历史', exact: true }).first().click()
  91  |   const history = await (await api.get(`/api/profile-facts/${second.id}/history`)).json()
  92  |   expect(history.items.map((item: { revision: number }) => item.revision)).toEqual([1, 2])
  93  |   await capture(page, 'facts-history-mobile', true)
  94  |   const removed = page.waitForResponse(r => r.url().includes('/api/profile-facts/') && r.request().method() === 'DELETE')
  95  |   await facts.getByRole('button', { name: '删除事实', exact: true }).first().click()
  96  |   const tombstone = await (await removed).json()
  97  |   expect(tombstone.revision).toBe(3)
  98  |   expect(tombstone.deletedAt).toBeTruthy()
  99  |   await facts.getByLabel('显示已删除事实', { exact: true }).check()
  100 |   await expect(facts.getByText('已删除', { exact: true }).first()).toBeVisible()
  101 | })
  102 | 
  103 | test('岗位解析错误保留原文可重试，筛选无结果有空状态', async ({ page, api }) => {
  104 |   const created = await api.post('/api/jobs', { data: { title: '解析重试示例', text: 'E2E_RETRY_PARSE 负责 API 和数据库设计。' } })
  105 |   const { job } = await created.json()
  106 |   await page.goto('/jobs')
  107 |   await page.locator(`[data-job-id="${job.id}"]`).click()
  108 |   const detail = page.getByRole('region', { name: '岗位详情', exact: true })
  109 |   await detail.getByRole('button', { name: '解析岗位', exact: true }).click()
  110 |   await expect(detail.getByRole('button', { name: '重试解析', exact: true })).toBeVisible()
  111 |   expect((await (await api.get(`/api/jobs/${job.id}`)).json()).text).toContain('E2E_RETRY_PARSE')
  112 |   await capture(page, 'jobs-parse-error-mobile', true)
  113 |   await detail.getByRole('button', { name: '重试解析', exact: true }).click()
> 114 |   await expect.poll(async () => (await (await api.get(`/api/jobs/${job.id}`)).json()).parseStatus).toBe('success')
      |                                                                                                    ^ Error: expect(received).toBe(expected) // Object.is equality
  115 |   await page.getByLabel('搜索岗位', { exact: true }).fill('没有匹配的岗位名称')
  116 |   await page.getByLabel('搜索岗位', { exact: true }).press('Enter')
  117 |   await expect(page.getByText('没有符合筛选条件的岗位。试试其他关键词或状态。', { exact: true })).toBeVisible()
  118 |   await capture(page, 'jobs-filter-empty-desktop')
  119 | })
  120 | 
```