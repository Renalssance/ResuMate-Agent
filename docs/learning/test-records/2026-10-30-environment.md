# 原工作区环境配置与旧环境清理

日期：2026-10-30。当前目录 `/Users/bono/Desktop/code/ResuMate-Agent`，分支 `codex/resumate-fullstack-learning`。沿用原main工作区的 `.env` 和 `.env.cloudbase`，不覆盖、不输出内容。原未提交修改继续保留。

## 当前环境

- Python 3.12.14，环境为项目根目录 `.venv`。
- `uv sync --frozen --group dev --extra telemetry --offline`：检查156个包，通过。包含开发与Langfuse依赖，OCR/本地embedding仍按需安装。
- 根目录及frontend分别执行 `npm ci --offline --no-audit --no-fund`：安装3和221个包，成功。
- 首轮使用系统Node 24.10.0，abbrev/nopt给出最低Node 24.15的engine警告。通过nvm安装Node 24.22.2，并写入项目 `.nvmrc`；使用npm 11.19.1完成后续验证。保留系统Node及其他项目默认版本。

在新终端进入项目后：

```sh
source ~/.nvm/nvm.sh
nvm use
source .venv/bin/activate
```

## 验证目的与结果

依赖一致性检查用于发现搬迁后缺包或版本冲突；若失败则按锁文件修正。`uv pip check --python .venv/bin/python`通过，FastAPI/Celery/Redis/Deep Agents/Langfuse可导入。Python和Node各实际启动一次Chromium，均为156.0.8078.4并正常退出，确认浏览器运行依赖可用。

更换Node后验证类型、测试及构建，避免仅以安装成功判断环境正常：`npm --prefix frontend test` exit0；组件28文件/177测试通过，3.04秒；生产构建exit0，Vite耗时1.50秒。以上包含原工作区尚未提交的资料模板修改，不改写早期冻结源码的验收结论。[原始输出](raw/2026-10-30-environment/)已保存。未启动业务预览、未请求付费模型，未重复后端全量业务回归。

## 清理范围

删除迁移备份中的旧 `.venv` 与旧frontend/node_modules、临时CloudBase工具node_modules，以及旧4173预览的两条依赖链接，共5处。保留源代码、原修改备份、SQL/checkpoint、截图及日志；[确切清单](raw/2026-10-30-environment/cleanup.json)。

关闭仅使用 `/tmp/resumate-mysql-t02/data` 的开发测试MySQL，保留数据及系统MySQL。移除旧frontend/backend的5cd2b8fd52镜像标签，保留最终d4cbbe972e-terminal/7a3122655a-lifecycle镜像及MySQL、Redis、nginx基础镜像。共享镜像层仍可能被最终镜像引用，不声称全部物理空间已释放。

删除后确认上述5处不存在、测试MySQL已退出。全局Python/Node、共享浏览器缓存及其他项目环境未清理。
