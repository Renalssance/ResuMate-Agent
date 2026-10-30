# T19 当前版本最终预览

当前服务持续运行，未录屏。旧 4173 服务保留。没有追加 T20 验收。

## 入口与账号

- 岗位页：http://127.0.0.1:4175/jobs
- 真实待补问任务：http://127.0.0.1:4175/agent/tasks/1c38996d-f673-428d-a16f-9e042257fb79
- 账号：`browser-fixture`
- 密码：`synthetic-browser-password`
- API：http://127.0.0.1:4176
- 扩展测试页服务：http://127.0.0.1:8898

账号、资料及模型均为合成演示数据。API、worker、SQL、checkpoint 和持久事件为实际代码；只有外部模型使用确定性测试实现，不调用付费供应商。已有一份合成简历、一个岗位及一条实际执行至 waiting_input 的任务，没有通过 SQL 伪造任务状态。未提交回答、未额外生成材料或面试。

## 基线与运行记录

- 源码目录：`/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`
- 基线：`cdde2c53c6a80e271c2d185bef80b179d8e2fcb7` 加已冻结、尚未提交的 T17/T18/T19 工作树变更。
- STATE：`/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49`
- 启动时间：`2026-10-30T12:13:29.814524+08:00`
- launcher PID：1327；API：1335；worker：1336；Vite：1356；扩展 fixture：1340。
- 原 4173 Vite PID：75022，未停止或改动。
- 当前 Redis：`d8463a1153b5 public.ecr.aws/docker/library/redis:7.4-alpine 127.0.0.1:55195->6379/tcp`

使用现有 tests/e2e/support/server.py 的独立副本 `/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/preview_server.py`：只固定源码根路径，并关闭退出时删除 SQL/checkpoint/原件的清理段，确保这次预览数据保留。产品代码没有修改。正常终止时该 launcher 会停止自己创建的子进程及 Redis，而不删除 STATE；当前没有终止。

元数据、启动及子服务日志：`/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/preview.json`、`launcher.log`、`api.log`、`worker.log`、`frontend.log`、`extension-fixtures.log`。监听端口快照：`listeners.txt`。

## 实际截图检查

以下四张最终截图均已通过 view_image 实际打开：

- `/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/screenshots/jobs-1440.png`：1440×1000 视窗，桌面导航、岗位收藏表单、岗位列表及详情均正常。
- `/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/screenshots/jobs-390.png`：390×844，表单及详情纵向排列，按钮可见，无横向溢出。
- `/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/screenshots/jobs-320.png`：320×844，窄屏按钮按需换行，无横向溢出或遮挡。
- `/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/screenshots/waiting-input-390.png`：390×844，实际历史事件加载后截图；显示读取岗位和简历已完成、补充真实经历等待回答。回答框空白，任务仍可继续。

原始观察：`/var/folders/6p/f3_2rt7d7lzfyks3z418lmdr0000gn/T/task-19-final-preview-wlvk8n49/browser-observations.json`。三个宽度 scrollWidth 分别等于 1440/390/320，浏览器 pageerror 为 0。待补问初始截图曾显示加载中，随后只等待实际 SSE 历史到达再重拍，并已再次实际打开最终图片；没有改 DOM 或业务状态。

本步骤仅验证预览启动与视觉，不重复全后端/浏览器验收。此前 root 已完成 jobs+recovery 6 场景复测。
