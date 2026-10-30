# ResuMate 浏览器扩展

扩展用于主动收藏岗位与辅助填表。浏览器中的每次收藏、字段选择和填入都由你发起，招聘网站上的最终提交仍需你手动完成。

## 安装与连接

1. 从主应用“浏览器插件”页下载 ZIP 并解压，或使用仓库中的 `extension/` 目录。
2. 打开 Chrome 的 `chrome://extensions` 或 Edge 的扩展管理页，开启开发者模式，选择“加载已解压的扩展”。
3. 点击浏览器工具栏中的 ResuMate 图标，打开侧边栏。
4. 展开设置，填写自己的后端地址（本地通常为 `http://127.0.0.1:8000`），用已有 ResuMate 账号登录。密码不会保存。
5. 可在顶部切换中文/EN，选择会保留。

## 收藏当前岗位

1. 打开一个岗位详情页，点击“读取当前岗位”。采集仅在你点击时发生，不会后台抓取网页。
2. 核对标题、公司、来源 URL 和正文，必要时编辑；随后点击“收藏岗位”。收藏本身不启动模型解析。
3. 同一账号再次收藏相同完整 URL 时，会返回已收藏岗位，并保留你在主应用中的整理。URL 的查询参数、片段与大小写仍属于来源，不自动合并不同网址。
4. 页面受限、无法读取或正文为空时，可以直接在侧栏粘贴文本，补标题后收藏；不需要绕过网站限制。
5. 回到主应用“岗位中心”查看、关联简历或主动解析。

收藏使用 `/api/jobs/capture`；原有 `/api/jobs` 导入的 URL+正文规则保持不变。通用采集不伪造站点岗位 ID，也不承诺适配所有招聘站。

## 选择简历版本并填表

1. 点击刷新，在下拉框选择“原简历”或“已确认版本”。草稿须先在主应用完成逐条审阅和确认，才能出现在这里。
2. 已确认版本使用确认时冻结的内容；主简历之后改变不会悄悄替换所选版本。标签显示版本修订号与创建时间。
3. 打开申请表单，点击“扫描页面”，查看匹配字段和值。
4. 取消不想填入的字段，再点击“填充选中项”。密码、验证码与文件上传不会被自动填写。
5. 回到网站检查结果，自行提交。扩展不会点击提交、自动创建投递记录或把“已填表”当成“已投递”。

页面、标签页、简历版本或连接设置改变后，需要重新扫描。暂时断网时可使用本账号已加载的缓存档案进行本地匹配；界面会提示缓存/离线。退出、换后端或登录失效会清除旧档案缓存。

## 本地示例与开发

```sh
# 根目录启动静态示例，使用已运行的真实后端登录：
node extension/fixtures/static-server.js
# 打开 http://127.0.0.1:8899/extension/fixtures/job-detail.html
# 表单 http://127.0.0.1:8899/extension/fixtures/application-form.html
```

表单示例显示手动提交次数，便于确认填入没有触发提交。原 `mock-autofill-api.js` 仍作为原始简历填表演示，不能代替收藏/确认版本的真实后端验收。

```sh
node --test extension/tests/*.test.mjs
npx playwright test tests/e2e/extension.spec.ts --project=chromium --trace off
```

浏览器测试自动使用临时 Chromium 配置、真实 MV3 worker/content script、独立 API/SQL 和合成数据，不使用你的日常浏览器账号。真实模型响应由测试入口替换，相关版本生成不产生付费调用。详细结果以仓库 `docs/learning/test-records/` 为准。

## English quick guide

Load the unpacked extension in Chrome/Edge developer mode, open ResuMate from the toolbar, set your backend URL and sign in. The password is not stored.

On a job detail page, choose **Read current job**, review/edit the visible text and source URL, then explicitly save it. Restricted pages can use pasted text. Repeated capture of the same complete URL returns the existing job without replacing your edits. Saving does not start model parsing.

Refresh profiles and choose an original resume or a **confirmed version**. Confirmed versions use their frozen content. Scan the application page, review the matched values, uncheck unwanted fields, and fill the selection. The extension never clicks Submit or creates an application record. Review the page and submit yourself.

Changing the page, selected version or connection invalidates the previous scan. Temporary offline matching uses only the loaded account's cached profile; logout, backend changes and expired authentication clear the cache.
