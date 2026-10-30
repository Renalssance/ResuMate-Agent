# T19 A：生产构建与真实备份恢复已完成

生产代码已冻结，无提交、无付费调用。根旧 CloudBase Dockerfile只修了 uv --no-cache 和过时内存事件注释，本次没有构建第三张镜像。实际 fresh 构建的是 Compose 使用的 backend/worker 与 frontend/nginx 两张生产镜像。

## 代码与定向验证

- `/healthz` 保留进程存活语义；`/readyz` 在线程中实际 SELECT 1，再 Redis PING，失败只返回 `not_ready`/503，不泄漏连接串。SQLite/MySQL 共 6 项：6 RED（缺路由）→6 GREEN/1.73s，`/tmp/task-19-readiness-{red,green}.txt`。
- 主 Compose 增加本机 127.0.0.1:8787 默认入口，可用 RESUMATE_WEB_PORT 改端口；保留 MySQL 8.4、双 API、Redis、单 worker、scheduler、共享业务卷、worker 独占 checkpoint 卷。实际模型/embedding/OCR 环境明确传入容器，个人 BYOK 仍由 SQL 设置。旧 Redis 集成 override 的 web 放进 tests-only profile，未重跑已经通过的 T20 七案。
- worker 使用锁文件、uv --no-cache、OCR extra 和 libgomp/libgl/glib、Playwright Chromium、中文字体。实际 fresh 容器中 RapidOCR 完成初始化、Chromium 156.0.8078.4 启动并生成 PDF；`runtime-probe.txt` 记录依赖版本，无供应商调用。
- `deploy/backup.py` 明确要求项目和 env 文件，停止入口、scheduler、worker 并确认无写入者，再导出 MySQL 和静止的完整业务/checkpoint 目录（包括 WAL）。恢复拒绝已有项目/卷，在全新项目启动。源项目写入者保持停止。root 独立源码审查未发现 P1/P2；以下实测才是行为验证。

## 逐次构建证据（不合并失败为成功）

全部原始目录为 `/tmp/task-19-build-<ID>`。

| ID | 实际结果 |
| --- | --- |
| a5454d0f71 | 依赖/OCR/Chromium/CJK 安装完成，镜像导出后的解包提交遇宿主 ENOSPC，Docker 元数据只读；backend/frontend built 均 false，前端未开始。完整 source/log 保留。 |
| 1c9d135ffa | 重启与回收后重建，Playwright 内部 apt 更新约 8 分钟无新输出；宿主和现有容器同源新请求均 200（容器 0.23s）。只终止该构建进程组，exit130；增加实际安装步骤 https Timeout=30 秒、Retries=2。 |
| 6738606881 | 镜像 metadata 前因本次执行器 PATH 找不到 docker-credential-desktop 退出1。只修执行器子进程 PATH，未改用户全局 Docker 配置。 |
| 5cd2b8fd52 | backend export/unpack 完成、exit0。frontend 开始时每秒监测发现低于2GiB阈值，主动停止exit130，原 build.json 保留。清理精确缓存/旧实验镜像后，同一冻结 source 单独续前端，frontend-retry.json exit0；没有重复后端构建。 |

最终生产源码：`/tmp/task-19-build-5cd2b8fd52/source`。镜像与源绑定记录 `delivery-images.json`：

- `resumate-t19-backend:5cd2b8fd52`，arm64，3,034,132,853 bytes，ID `sha256:83629f6b72ea003153d037cb314228ab268dc6f04f05360d05555fa544dd9455`。
- `resumate-t19-frontend:5cd2b8fd52`，arm64，98,777,161 bytes，ID `sha256:9a800b9b4bb2be0199570a36fd01d71ba8a54537b489a391e5d79454475bbbf0`。

宿主维修与回收严格限于本项目：root先用SQLite在线backup API保全预览数据并恢复native MySQL/预览Redis；本代理完成Docker Desktop重启。先清首次失败8条精确cache约2.753GB，再清无容器使用旧T04 agentworker镜像/4条cache约1.323GB。后端成功后清本轮6条cache约2.965GB；实际OCR/Chromium核验通过后，按root明确授权清无容器引用的旧T11/T20 aligned及其6条旧cache约3.34GB。旧SHA/日志均保留，没有把新镜像重标旧tag，没有全局prune、删用户卷、改Docker全局内存或运行privileged回收工具。后续opt-in Compose测试显式使用新镜像参数。

## 真实部署、备份、恢复

第一轮 `/tmp/task-19-delivery-first.txt`：1 failed/58.42s，证据目录 `/tmp/task-19-artifacts-609ad187f2374c23b866b2631625775c`。Redis/MySQL断开503及恢复200已过；PDF POST401。真实根因是pytest conftest父进程的JWT_SECRET_KEY通过shell优先级覆盖Compose --env-file，而客户端用随机项目secret签名。仅修测试子进程环境，让对应文件的键生效，并补合法exp；未改生产鉴权、未绕过认证。

第二轮 `/tmp/task-19-delivery-second.txt`：**1 passed/91.96s**，同一fresh生产镜像；证据 `/tmp/task-19-artifacts-9ad7a2f23b2c48e49299126f985dd6dc`，executed=true、status=pass、completed=true。

- 两个独立项目，真实MySQL/Redis/nginx/API/worker/scheduler；只挂载测试目录注入确定性模型，没有挂载生产backend覆盖镜像。
- Redis停机、MySQL停机分别 `/readyz` 503，而 `/healthz` 200；依赖恢复后readyz 200。
- 实际API导出已确认版本，生产Chromium生成两页中文PDF；两张PNG已实际打开逐页查看：中文、层级、换行正常，无缺字、重叠或裁切。PDF产物恢复后字节完全一致。
- Run `c0ff09db-ac6c-4bf2-80f3-ad8862845f2a` 在 waiting_input、4条图消息、待tools节点和真实interrupt时备份；新项目恢复后同Run、同session、同action、同7条SQL事件、同checkpoint。
- 新项目回答原补问后succeeded，图10条消息且无剩余节点；18条SQL事件中artifact.created恰好1条，ResumeVersion=1、ToolOperation=1。原简历文件、实际Chroma记录及PDF数量/内容保持。
- 两项目均 down --volumes code0；进一步只按其project标签查询，容器0/卷0。`cleanup-verification.json`记录，最后检查宿主8.98GiB余量。已把运行窗口交给E执行新的四项恢复；本代理不重复全量套件或浏览器。

## 可归档与私有边界

公开准备目录：`/tmp/task-19-delivery-public`，README解释每一来源。包括逐次失败/成功txt/json、对应Dockerfile/锁文件、最终完整生产构建source、实际执行测试脚本、两轮集成、合成业务备份、两页PDF截图、定向红绿。

- 明确排除8个build.env/项目.env文件，内含随机JWT/MySQL凭据；不入Git。source/.env.example只是公开模板。
- backup/mysql.sql和两个tar.gz均来自delivery.seed/确定性模型：虚构账号、合成简历/JD/Chroma/中文PDF/checkpoint，不含真实用户/BYOK。备份脚本用于真实数据时，SQL和卷当然应按私有数据保管。
- 对493个已选公开文件及解压读取的两个备份内容检查已知实验secret，匹配0；txt/json/sql JWT令牌匹配0。只记录数量，不输出密钥。`archive-privacy.json`保存结果。
- 首轮构建失败source仍完整留在各自/tmp；公开包只为每次失败保留相关构建配置/锁文件，完整最终source保存一次。实际GREEN测试driver在integration/final-pass/executed-test_delivery_compose.py；它在镜像构建后修复了夹具环境，生产镜像未改变。

全后端、普通31项浏览器及E四恢复/30案由root/E依序执行，本报告不将这些尚在其他代理执行的结果计入本单元。

## 后续客户端生命周期源码修订镜像

T18独立审查确认显式模型传输客户端丢失上游自动关闭语义；最小修复经过26项传输/生命周期及74项关联回归，并由root独立审查。产品模型依赖、操作系统依赖、worker Dockerfile没有改变。

在root批准的独立窗口，以原已fresh验收镜像 `resumate-t19-backend:5cd2b8fd52` 为基础，仅 COPY 完整冻结 backend 生成源码修订镜像 `resumate-t19-backend:7a3122655a-lifecycle`，ID `sha256:eda8e67eef1ab340f033ad368d00b10bcc43009fae0ff32bb32df152cc670f89`（arm64，3,035,173,644 bytes）。这是对已fresh基础的透明源码更新，不称为生产Dockerfile重新fresh全装。

完整证据 `/tmp/task-19-backend-revision-7a3122655a`：两行修订Dockerfile、完整backend源码快照、原部署配置/锁文件、执行器、无凭据命令、构建日志、镜像绑定revision.json。新镜像内实际运行SDK探针，无生产源码挂载，8项同步/异步、307/308、GC/显式关闭全部通过，保留timeout7/max_retries0；`runtime-probe.{py,txt,json}`记录。未重新跑无关备份/四恢复，原fresh与首次失败证据完全保留。

本次构建无依赖下载、无清理操作；余量从约7.52GiB到6.67GiB，未触发2GiB保护阈值。窗口已交还root浏览器复测。前端终态显示的独立修复由A完成，后续完整frontend.Dockerfile构建见下节，原前端镜像证据保留。

## 最终前端与镜像组合

A的前端终态修复冻结后，root受影响浏览器6 passed/32.2s；原完整31项为30 passed/1 failed，随后单独补测，不记为同轮31全绿。

以完整 `deploy/frontend.Dockerfile` 对冻结源码执行正常构建（复用Docker缓存），生成 `resumate-t19-frontend:d4cbbe972e-terminal`，ID `sha256:3d116c901b06f02b3ac685c494ddf3a279d6b5a9ec9912bd6b86d21eae4c9b39`，arm64，98,776,445 bytes。实际type/Vite build与镜像导出exit0，证据 `/tmp/task-19-frontend-final-d4cbbe972e` 保存完整输入源码、Dockerfile、执行器、命令及日志。

临时新nginx容器中首页200，新主脚本243,490 bytes与CSS93,322 bytes均200，CSP及nosniff正常。api/api2使用该测试容器的显式本机host映射，仅检查静态服务，不冒充完整依赖就绪验收。容器精确清理exit0，`runtime-probe.json`与`nginx-runtime.txt`保留。没有修改生产nginx。

最终镜像绑定 `/tmp/task-19-final-images.json`：backend=`7a3122655a-lifecycle`，frontend=`d4cbbe972e-terminal`。旧fresh与全部逐次失败证据保留。本代理所有源码/镜像工作已冻结，运行窗口交给A启动最终4175预览；不录制演示视频，不追加已取消必做要求的T20实验，不回滚现有Redis依赖。
