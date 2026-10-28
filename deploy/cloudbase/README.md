# ResuMate 部署到 CloudBase 云托管 + MySQL

复用国内站上海环境 `dev-d0g73fv8v22380036` 的云托管、MySQL 和传统云存储。AI 使用项目自配的 Model / API Key / Base URL 与 `EMBEDDING_*` 配置，保留现有 Vue、FastAPI、SQLAlchemy、JWT 登录、文档解析、匹配、面试问题、投递管理、SSE 和扩展 API。

## 架构

```text
浏览器 / ResuMate 扩展
  → CloudBase HTTPS 入口
    → 单实例 FastAPI :8000（同时提供 Vue 生产页面）
      → CloudBase MySQL 172.17.0.11:3306：业务表 + JSON 文档向量
      → CloudBase 传统私有云存储：简历、JD 原文件
      → 项目配置的 LLM API：文档解析、匹配、问题生成、聊天
      → EMBEDDING_* 配置的远程 embedding API
```

前端继续通过 `/auth`、`/api` 访问后端；保留 ResuMate 账号系统。数据库密码与 CloudBase 服务端 API Key 只注入服务端。MySQL 表经 SDK/HTTP 数据接口的权限设置为仅管理员，业务接口继续按 JWT 用户和 `user_id` 过滤。

文档向量与原文片段存入 MySQL JSON 表。检索先通过复合主键按用户、简历 ID、文档类型过滤，再在云托管进程计算余弦 top-k。当前流程每次检索一份简历，无需新增向量数据库；计算量随该简历的片段数增长。

云模式由 `CLOUDBASE_ENV_ID` 启用，用于选择 MySQL 和云存储。LLM 沿用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL`，也兼容项目原有的 `ARK_API_KEY`、`BASE_URL`、`MODEL` 别名。用户可以在设置页自定义 Model、API Key、Base URL 及生成参数；保存的个人设置优先于服务端默认值。Embedding 沿用 `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`。镜像安装 OCR 依赖，运行时调用配置的远程模型服务。

原文件经后端获取 CloudBase 临时上传签名，上传到环境内置的 COS 存储，数据库保存原生 `cloud://` fileID；不创建独立 COS 桶。上传解析结束后清理本地缓存。重解析时通过临时下载 URL 获取文件，临时请求不携带服务端 API Key。

## 已部署资源

应用地址：[ResuMate](https://resumate-agent-330043-10-1317520624.sh.run.tcloudbase.com)。浏览器扩展的 Backend 也填写此地址。

2026-10-17 已完成线上验收，当次发布版本为 `004`：注册登录、投递记录读写、简历/JD 上传解析、从旧版本云存储原文件重解析、匹配、问题生成、追问分析、MySQL 证据检索、聊天流和扩展资料接口均已验证。简历解析 86.4 秒、旧文件重解析 80.5 秒、问题生成 116 秒均通过异步任务与 SSE 完整返回；最终匹配的即时列表与持久化结果一致，跨版本的报告与问题仍可读取。

2026-10-18 发布版本 `005`：新增论文与获奖经历资料编辑、字段框内的复制图标，并将前端图标统一为 Lucide。发布前前端测试、生产构建及后端健康检查和结构资料保存测试通过；发布后已确认健康接口正常、线上 CSS/JS 与本次构建一致，CPU/内存、单实例、VPC、访问类型和全部运行变量均保持原配置。

2026-10-26 当前发布版本为 `006`，已承载 100% 流量。发布前后端 219 项测试、前端完整测试及生产构建通过；发布后 `/healthz`、首页和 `/documents` 均正常，线上静态资源名与本次本地构建一致。服务继续使用 1 CPU / 2 GB、单实例、端口 8000、原 VPC 与子网，以及原有 18 项运行变量。

已通过管理接口确认：

- MySQL 状态 `running`，版本 `8.0.30-cynos-3.1.19.002`。
- 当前数据库为 `dev-d0g73fv8v22380036`；初始化前为空库，现已创建并核验 17 张应用表。
- 用户提供的内网地址 `172.17.0.11:3306`。
- 数据库 VPC 为 `vpc-nyo6dl3g`（`172.17.0.0/16`），子网 `subnet-nyqchgv3`（`172.17.0.0/20`）。
- 云托管环境已存在且状态 `normal`。

当前服务使用用户提供的 MySQL `resume` 账号，已验证注册与业务数据读写。数据库密码、独立签发的服务端 API Key 及原有模型凭据保存在本机私有 `.env.cloudbase` 并注入云托管，不在源码包中。Embedding 使用 `qwen3.7-text-embedding-flash`，实测输出 1024 维向量。

2026-10-17 已另行迁入本地 `data/resumate.db` 的 291 条业务记录：原账号、3 份简历、1 份 JD、91 条投递、139 条原状态记录、32 条日程及历史分析/报告/问题/个人模型设置。保留原 ID 和关联；4 份原文件已存入私有云存储并下载逐字节核对，38 个检索片段已按用户授权用 Flash 模型重建。迁移后产生的云端新编辑予以保留。本地原库未改动，私有快照和验收报告位于 `data/cloudbase-migration/20261017-132557/`，不提交到 Git。原有两次 `running` 分析只保留历史记录，不会自动恢复执行。

## 1. 初始化现有 MySQL

`deploy/cloudbase/mysql-schema.sql` 包含 17 张应用表及索引，使用 MySQL JSON、InnoDB、utf8mb4；文档及聊天内容用 LONGTEXT，避免普通 TEXT 的 64 KiB 上限。每张表包含 CloudBase SDK 元数据列 `_openid`，业务权限仍使用现有 `user_id`。当前 dev 环境已执行该脚本，勿再次初始化；17 张表的 CloudBase 权限已确认均为仅管理员。

脚本不使用 `IF NOT EXISTS`、不删除或修改现有表，不包含历史 SQLite 数据和本机原文件搬迁。执行前先检查真实表结构；若发现同名表，不直接执行初始化脚本，先确认是否为已有应用数据。

```bash
tcb db execute --env-id dev-d0g73fv8v22380036 --sql "SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA = 'dev-d0g73fv8v22380036'" --read-only --json
```

通过 CloudBase MySQL SQL 编辑器或管理 API 按脚本顺序执行建表语句；这不是 PostgreSQL migration，不能使用 `tcb db pg migration`。建表后通过 CloudBase 权限管理将这些应用表设为仅管理员可读写，并验证普通客户端不能读取账号、文档或模型配置。

应用云端启动只连接并检查已初始化的用户表，不自动执行 DDL。后续结构变更须显式执行相应 SQL。现有 MySQL 不需要迁移或替换为新数据库产品。

## 2. 配置服务端运行变量

参考 `runtime.env.example`。本地用于部署的真实配置可放仓库根目录 `.env.cloudbase`（已被 Git 和源码包排除），权限设为 `600`。将用户原有的模型、API Key、Base URL 和 embedding 配置写入这个部署配置，保留本地 `.env`；服务端的默认模型参数与设置页的个人配置继续生效。

连接串使用用户提供的格式：

```text
mysql://[DB-USERNAME]:[DB-PASSWORD]@172.17.0.11:3306/dev-d0g73fv8v22380036
```

应用自动选择已安装的 `mysql+pymysql` 驱动并使用 `utf8mb4`；可直接使用 `mysql://`。用户名、密码中的 `@`、`:`、`/` 等字符需 URL 编码。数据库是内网地址，本机不能据此完成真实连接测试，必须在同网络的云托管实例验证。

CloudBase 服务端 API Key 使用本环境独立签发的应用 Key，注入 `CLOUDBASE_APIKEY`，仅供私有文档存储调用；模型 API 使用项目自配的凭据。不能复制 CLI 登录短期凭据，部署时需验证该 Key 的存储权限。不要通过放开匿名存储权限来解决服务端认证问题。

## 3. 构建和部署云托管

仓库根目录的 `Dockerfile` 构建 Vue，再安装锁定的 Python 和 OCR 依赖。Docker 上下文采用允许列表，不包含 `.env`、数据库、日志或测试。默认镜像不安装可选的本地 embedding 依赖，也不下载模型权重。

```bash
sh deploy/cloudbase/package.sh
```

产物 `build/cloudbase/resumate-cloudbase-source.tar.gz` 可用于 CloudBase 云托管源码构建，构建目录必须是含 Dockerfile 的仓库根目录。镜像由 CloudBase 托管构建和存储；已在云端完成完整镜像构建并启动服务。

| 项目 | 配置 |
| --- | --- |
| 服务 | `resumate-agent`，容器模式 |
| 端口 | `8000`，监听 `0.0.0.0` |
| 健康检查 | HTTP `/healthz`，固定 JSON `{"status":"ok"}` |
| 进程 | 镜像默认 Uvicorn，一个 worker |
| 实例 | 最小 1，最大 1 |
| 起始资源 | 1 CPU / 2 GB，部署后按解析任务的实际内存使用调整 |
| VPC / 子网 | `vpc-nyo6dl3g` / `subnet-nyqchgv3`，与本环境 MySQL 连通 |
| 变量 | `runtime.env.example` 中各项的实际值 |
| 入口 | CloudBase 默认 HTTPS 入口，保持路径并支持 SSE |

CLI 源码部署命令形态如下，**必须先通过控制台或 Manager SDK 注入实际环境变量并确认服务网络配置**，不能省略这些前提直接运行示例：

```bash
tcb cloudrun deploy --env-id dev-d0g73fv8v22380036 --service-name resumate-agent --source . --port 8000 --min-num 1 --max-num 1 --vpc-config '{"vpcId":"vpc-nyo6dl3g","vpcCIDR":"172.17.0.0/16","subnetId":"subnet-nyqchgv3","subnetCIDR":"172.17.0.0/20"}' --wait
```

`tcb cloudrun deploy` 没有环境变量参数。通过控制台或 Manager SDK 的 `serverConfig.EnvParams` 注入密钥，勿写入镜像，也勿编造 `--env` 参数。发布时同时检查真实 CPU/内存配置，CLI 示例本身不设置这些资源。

现有任务进度和限流计数保存在内存，因此当前必须固定单实例、单 worker。更新服务前等待解析、匹配和问题生成结束；进程重启会中断进行中的任务，已完成的数据和原文件持久保存。日志写 stdout 进入云托管日志；本地轮转日志不作为业务持久数据。

云托管普通请求的超时为 60 秒。前端的文档上传/重解析、匹配、问题生成发送 `Prefer: respond-async`，接口先返回 `202 {"taskId":"..."}`；后台使用独立数据库会话执行原业务，前端通过 `/api/tasks/{taskId}/events` 的终态数据取得原结果。追问分析接口也支持同一提交方式。未发送该请求头的 API 调用保持同步协议，长模型调用仍可能受到网关超时限制。进度与聊天 SSE 每 15 秒发送空闲心跳。

## 4. HTTPS 和验收

当前已发布的云托管 HTTPS 地址：

```text
https://resumate-agent-330043-10-1317520624.sh.run.tcloudbase.com
```

该地址已加入实际服务的 `CORS_ORIGINS`。环境默认网关域名尚未绑定 ResuMate；如需另绑域名，先检查是否已有其他应用占用，不覆盖已有路由。

默认域名在浏览器中会显示 CloudBase 访问提示页，供开发测试。正式使用须绑定已完成 ICP 备案的自定义域名；这是平台移除中间页的方式，参见[默认域名访问限制及中间页](https://docs.cloudbase.net/service/alias)。

发布后验证：

1. `/healthz` 返回 JSON，`/`、`/documents`、`/applications` 显示 Vue 页面。
2. 注册登录 ResuMate，上传测试简历和 JD；确认云端原文件、MySQL 记录、匹配、证据检索、问题生成、聊天及 SSE 正常。
3. 等任务结束后重启云托管版本，再登录、读取文档及检索；重新解析原文件，证明不依赖旧容器磁盘。
4. 扩展切换最终 HTTPS 地址，验证列表刷新和测试表单填充。

失败时先检查 VPC、数据库账号权限、CloudBase 存储权限，以及自配模型 API 的地址和凭据。回滚应用使用上一正常版本，不自动删除数据库表或数据。

官方依据：[MySQL 内网直连](https://docs.cloudbase.net/database/configuration/db/tdsql/direct-connection)、[云托管接入 MySQL](https://docs.cloudbase.net/run/develop/resource-integration/mysql)、[传统存储 HTTP API](https://docs.cloudbase.net/http-api/storage-overview)。
