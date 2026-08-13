# ResuMate Autofill Extension

## 中文使用说明

### 安装插件

1. 打开 Chrome 或 Edge。
2. 进入 `chrome://extensions`。
3. 打开右上角的 Developer mode。
4. 点击 Load unpacked。
5. 选择本仓库里的 `extension/` 目录。
6. 打开任意招聘申请页面，点击 ResuMate 插件图标。

### 切换语言

侧边栏顶部有 `中文 / EN` 切换按钮。选择会自动保存，下次打开插件会继续使用上一次的语言。

### 首次配置

1. 展开侧边栏里的 Settings。
2. Backend 填写后端地址，例如 `http://127.0.0.1:8000`。
3. 输入已有 ResuMate 账号的用户名和密码。
4. 点击 Log in / 登录。插件会保存登录返回的 JWT，但不会保存密码。
5. 点击 Refresh，插件会从 ResuMate 数据库读取当前用户已存储的简历。

### 切换简历

1. 在 `简历 / Stored resume` 下拉框中选择要用于填表的简历。
2. 下拉框中的数据来自 ResuMate 后端 `/api/autofill/profiles`，也就是数据库里的 `Resume` 记录。
3. 每个选项会显示简历名称、可填字段数和更新时间。
4. 切换简历后，旧扫描结果会立即失效，需要重新点击 Scan page / 扫描页面。
5. 如果没有简历，请先在 ResuMate 主应用中上传并解析简历，再回到插件点击 Refresh。

### 自动填充流程

1. 打开招聘网站的申请表单页面。
2. 在插件侧边栏选择要使用的已存储简历。
3. 点击 Scan page / 扫描页面。
4. 检查 Matched fields / 匹配字段列表。
5. 取消勾选你不想填写的字段。
6. 点击 Fill selected / 填充选中项。
7. 回到网页确认填写结果，再由你手动提交。

### 安全边界

- 插件只填充你勾选的字段。
- 插件不会自动点击提交按钮。
- 密码、验证码、文件上传等敏感字段会被跳过。
- 页面 URL、活动标签页、简历或 Settings 变化后，需要重新扫描再填充。
- 离线时会尽量使用缓存档案做本地匹配。

### 本地示例

1. 启动 ResuMate 后端，或使用 fixture mock API。
2. 加载 unpacked extension。
3. 打开 `extension/fixtures/application-form.html`。
4. 在插件中设置 Backend，并使用已有 ResuMate 账号登录。
5. 点击 Refresh、Scan page、Fill selected。
6. 确认普通字段被填写，验证码字段未被填写，提交按钮未被点击。

## English Guide

### Install The Extension

1. Open Chrome or Edge.
2. Go to `chrome://extensions`.
3. Enable Developer mode.
4. Click Load unpacked.
5. Select the `extension/` directory in this repository.
6. Open a recruiting application page and click the ResuMate extension icon.

### Switch Language

Use the `中文 / EN` toggle at the top of the side panel. Your choice is saved automatically and reused next time.

### First-Time Setup

1. Expand Settings in the side panel.
2. Set Backend, for example `http://127.0.0.1:8000`.
3. Enter the username and password for an existing ResuMate account.
4. Click Log in. The extension stores the returned JWT, but never stores the password.
5. Click Refresh. The extension will load the current user's stored resumes from the ResuMate database.

### Switch Resume

1. Choose a resume from the `Stored resume / 简历` dropdown.
2. The dropdown is loaded from the ResuMate backend `/api/autofill/profiles`, backed by the database `Resume` records.
3. Each option shows the resume name, fillable field count, and update date.
4. After switching resumes, previous scan results are invalidated. Scan the page again before filling.
5. If there are no resumes, upload and parse a resume in the main ResuMate app, then click Refresh in the extension.

### Autofill Flow

1. Open a job application form.
2. Choose the stored resume in the side panel.
3. Click Scan page.
4. Review the Matched fields list.
5. Uncheck any field you do not want to fill.
6. Click Fill selected.
7. Review the page yourself and submit manually.

### Safety Boundary

- The extension fills selected fields only.
- The extension never submits applications.
- Password, captcha, file upload, and other sensitive fields are skipped.
- If the page URL, active tab, Profile, or Settings changes, scan again before filling.
- When offline, the extension can use cached profiles for local matching.

### Local Demo

1. Start the ResuMate backend, or use the fixture mock API.
2. Load the unpacked extension.
3. Open `extension/fixtures/application-form.html`.
4. Set Backend in the extension and log in with an existing ResuMate account.
5. Click Refresh, Scan page, and Fill selected.
6. Confirm normal fields are filled, captcha remains unchanged, and the submit button is not clicked.
