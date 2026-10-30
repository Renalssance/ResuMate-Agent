# 本机部署与恢复

当前状态：2026-10-30完整生产Dockerfile的后端、前端镜像均已实际构建并解包成功，独立备份恢复演练1 passed/91.96s。完整fresh基线镜像为resumate-t19-backend:5cd2b8fd52与resumate-t19-frontend:5cd2b8fd52。随后HTTP客户端生命周期修复以该已验收backend为基础COPY当前backend，生成resumate-t19-backend:7a3122655a-lifecycle，镜像内8项真实SDK传输/关闭探针通过。此修订复用不变的OS与锁定依赖，不称重新全量fresh安装。首轮构建ENOSPC、依赖安装挂起、执行器PATH缺失和前端空间保护停止均分别留证，不覆盖为成功；最终四处进程恢复与完整回归另见T19记录。

## 部署边界

单机MySQL、Redis、双API、一个worker执行槽、scheduler和nginx。SQL保存业务事实；worker独占SQLite checkpoint卷。原文件、导出PDF和Chroma共用backend-data卷。Redis队列可以由SQL恢复扫描补投递；备份仍必须包含SQL、checkpoint和文件。

Docker业务进程均使用容器里的MySQL，不让宿主与容器混读SQLite WAL。原生开发则API与worker都在同一宿主。已有CloudBase配置继续保留，本次不宣称云部署完成。

## 配置与启动

在仓库根目录按`.env.example`准备本地`.env`，已有文件不要覆盖。至少填写`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`和`JWT_SECRET_KEY`；`ADMIN_INVITE_CODE`默认空，邀请注册需操作者明确设置。密码会进入数据库连接URL，使用随机十六进制值可避免URL特殊字符。模型及embedding分别配置，不能把聊天模型Key默认视为向量模型授权。

模型Key/URL/名称也可通过账号设置保存；真实请求会使用实际供应商额度。文档解析整次尝试上限120秒，单文件10MiB、PDF100页。OCR可通过已有PDF_OCR设置开启；镜像安装其运行依赖，默认不自动启用。默认不安装可选本地sentence-transformers模型。

```sh
docker compose --env-file .env -f deploy/compose.yaml build
docker compose --env-file .env -f deploy/compose.yaml up -d --wait
```

本机已有本轮验收过的镜像，可在独立的环境文件中指定以下两项，再使用`up -d --no-build --wait`，无需马上重新构建：

```dotenv
RESUMATE_BACKEND_IMAGE=resumate-t19-backend:7a3122655a-lifecycle
RESUMATE_FRONTEND_IMAGE=resumate-t19-frontend:d4cbbe972e-terminal
```

这些tag只存在于当前本机，没有推送镜像仓库；其他机器仍需执行完整构建。Compose的shell环境优先于`--env-file`：若终端已导出同名变量，应先核对实际配置，避免以为环境文件覆盖了一切。本次恢复夹具就因此先得到401，修正夹具环境和完整token后通过。

默认页面为`http://127.0.0.1:8787`，API为8000/8001且只绑定本机；可用RESUMATE_WEB_PORT/RESUMATE_API_PORT/RESUMATE_API2_PORT避免与现有开发服务冲突。MySQL与Redis不公开端口。不要把本机地址默认开放到公网。

`/healthz`表示进程能响应；`/readyz`实际读取SQL与Redis，依赖不可用返回503且不泄漏连接串。web健康检查通过真实代理访问readyz。共享数据库初始化由schema一次性服务先执行。

nginx提供前端生产文件和同源API/SSE代理，SSE关闭缓冲，60秒读超时大于15秒心跳；普通请求310秒。代理请求体上限11MiB给multipart留边界，API仍按文件字节严格限制10MiB。当前文字面试采用HTTP命令/快照，T21已取消，没有WebSocket入口。

## 停止与备份

备份脚本只操作显式项目，先停止web/API，再停止scheduler与worker并给130秒结束窗口；确认这些服务全部停止才导出。SQL用mysqldump；checkpoint和原文件/产物卷在静止后完整打包，包含可能存在的WAL。备份目录以私有权限创建，含账号和业务材料，不要提交到Git。外部.env由操作者另行保管。

```sh
python deploy/backup.py backup /absolute/path/resumate-backup --project resumate-agent --env-file .env
```

备份后源服务保持停止，检查结果后用前述up命令继续运行。不要用`down -v`停止正式资料项目，该选项会删除卷。

## 独立恢复演练

恢复必须使用没有容器和卷的新项目名，且环境文件指定不冲突端口及同一数据库凭据。脚本拒绝覆盖已有目标。先启动目标MySQL/Redis、导入SQL与文件/checkpoint，再启动应用，未完成Run由原扫描机制继续。

```sh
python deploy/backup.py restore /absolute/path/resumate-backup --project resumate-restore-check --env-file /absolute/path/restore.env
```

本轮已完成这些核对：同一Run/session/checkpoint/待回答动作和事件在新项目完整恢复，回答后任务succeeded，草稿版本、ToolOperation、artifact.created各1；原文件与Chroma内容保持，生产镜像导出两页中文PDF。实际断开Redis或MySQL时readyz为503、healthz仍200，依赖恢复后readyz回到200。两套实验项目和卷已按项目名清理，不操作用户预览数据。首次401失败与后续通过是两次独立记录。

## 构建空间故障的教训

镜像下载层、BuildKit中间层和解包后的最终镜像可能同时占用空间，不能只按最后镜像大小准备磁盘。本轮从约8.9GiB可用开始仍耗尽，导致Docker元数据只读，并使并行本机测试无法写入。后续重构建与重负载串行，先明确可用空间和本项目可回收缓存；不删除其他项目镜像/卷或重建Docker磁盘文件。测试失败、环境退出和实际产品失败分别留证。


只清本项目明确可回收的缓存后，Docker虚拟磁盘可能稍后才把空间还给宿主。T11与T20旧实验镜像共享约3.619GB层，删除一个几乎没有收益；在新镜像OCR/Chromium实际运行通过后，删除两张均无容器引用的旧镜像和其精确缓存，恢复足够运行空间。旧源码、镜像ID与历史证据保留，没有把新镜像重标为旧实验。之后运行旧opt-in实验时，用RESUMATE_PDF_BASE_IMAGE、RESUMATE_RECOVERY_IMAGE或RESUMATE_REDIS_BASE_IMAGE明确选择当前镜像。

有关Docker虚拟磁盘与回收行为，参考[Docker Desktop官方说明](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/macfaqs/)。本轮未全局prune、未缩小或删除Docker.raw，也未执行官方privileged回收容器；最终空间由精确清理和自动回收释放。

本轮实测原始资料见[交付证据目录](learning/test-records/raw/2026-10-30-t19/delivery/README.md)与[恢复前后记录](learning/test-records/raw/2026-10-30-t19/delivery/integration/final-pass/evidence.json)。

后续客户端修复的镜像、准确源码和运行探针见[后端修订镜像](learning/test-records/raw/2026-10-30-t19/backend-revision/README.md)。旧备份恢复未重复执行，不把旧结果改写为修订镜像运行。最终前端resumate-t19-frontend:d4cbbe972e-terminal已用完整生产Dockerfile构建，并在新nginx容器验证页面/JS/CSS均200及CSP/nosniff正常，见[最终前端镜像](learning/test-records/raw/2026-10-30-t19/frontend-final/README.md)。静态探针不冒充API就绪测试。
