# T17 前端单元 A 完成报告

日期：2026-10-30。工作树 `/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent`；任务基线 `cdde2c5`。未提交。未修改页面、后端、主计划或 Vite chunk 警告阈值；4173 预览保持运行。浏览器性能与是否需要虚拟化待根代理明确分派后实测，本报告不声明这些预算已通过。

## 变更

- `frontend/src/router/index.ts`：14 个路由记录、13 个视图使用动态导入；URL、命名、meta、滚动和标题行为保持。
- `frontend/src/stores/agentRun.ts`：100 ms 或 100 条先到即提交的有界事件批次；stream 已保证连续 seq，store 按 lastEventSeq 去重，避免每条事件线性扫描全部历史。一次批次只触发一次详情+产物读取；在途刷新合并后续批次，并在先前响应未覆盖后到 seq 时补查。订阅快照直接采用，仅加载 artifacts，消除首次重复快照请求。切任务/账号/断开清空计时器与批次；游标 reset 清空旧批次与历史。终态和 pending action 仍由 SQL snapshot 决定，未从重放事件推导状态；没有深拷贝事件历史或新增无界缓冲队列。
- `frontend/src/services/agentStream.ts`：online 唤醒现有 consume 循环的退避等待并清除原计时器。记录 online 代次，覆盖 offline reader 尚在关闭时就恢复联网的真实路径。online 不直接启动第二个循环；close/finally 清除监听器、计时器。429 Retry-After 保持执行。
- 对应 `agentRun.spec.ts`、`agentStream.spec.ts` 与新增 `router/index.spec.ts`：共新增 13 案，既有 29 案保留。

## 验证与原始证据

每项检查目的：RED 复现立即逐条更新/重复详情请求/online 不唤醒/同步路由；GREEN 检查修复且不丢有序 seq、终态或待补问；类型构建检查异步路由是否可编译和实际产物体积。

1. 修改前 `npm --prefix frontend run build`：exit 0。主包 `index-PWzqOdzq.js` **816.47 kB / gzip 305.25 kB**，出现默认 500 kB chunk warning。
   - 原始：`/tmp/task-17-frontend-build-before.txt`
2. RED，3 个定向 spec：**11 failed / 31 passed（42 总计）**，exit 1。失败为未实现的批处理/多余快照请求、懒加载和 online 两条恢复路径。合并在途请求用例也暴露初始多余快照响应覆盖状态，导致后续事件未触发预期刷新。
   - 原始：`/tmp/task-17-frontend-red.txt`
3. GREEN，同一 3 spec：**42 passed**，exit 0，1.19 s（Vitest 总时长）。初轮路由用例出现 jsdom 未实现 scrollTo 提示，补齐实际滚动断言等待后，该路由 spec **2 passed**（不是另加 2 个用例），无提示。
   - 原始：`/tmp/task-17-frontend-green.txt`
   - 路由测试修正后原始：`/tmp/task-17-frontend-router-green.txt`
4. 最终 `npm --prefix frontend run build`（包含 `vue-tsc --noEmit`）：exit 0。主包 `index-BLd1jQZE.js` **243.49 kB / gzip 86.26 kB**。分别减少 **572.98 kB（70.18%）/ 218.99 kB（71.74%）**。最大 JS chunk 是延迟加载的 `search-xpqiJ612.js` 303.52 kB / gzip 139.53 kB，未出现默认体积警告。
   - 原始：`/tmp/task-17-frontend-build-after.txt`

未运行全前端/全 E2E。实际输入延迟、浏览器事件到达时间、恢复联网耗时、DOM 容量尚未测量，后续生产 nginx 测量必须另行记录。没有据构建体积推定这些预算通过。
