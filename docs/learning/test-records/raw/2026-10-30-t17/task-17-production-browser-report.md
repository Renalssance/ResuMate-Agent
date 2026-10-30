# T17/T18 生产浏览器报告

前端单元报告：/tmp/task-17-frontend-report.md。浏览器验证使用当前 dist 的独立副本、真实 Nginx（官方 ECR镜像 public.ecr.aws/docker/library/nginx:stable-alpine，E实测1.30.6）、真实API/SQLite/独立Celery worker/Redis/SDK graph；仅外部模型与embedding为合成替代。CSP配置不改，仅两个upstream地址换成host.docker.internal:4274。Mac arm64宿主10 CPU、Playwright1.64.1，无4vCPU/8GB限制，不能替代E共享MySQL双API负载结论。4173稳定预览未动。

## 执行证据

- 首轮：/tmp/task-17-production-browser-yxK240。2案：1failed/1passed，raw.txt/playwright-results.json/服务日志/dist/nginx配置/trace.zip/video.webm/截图均完整保留。
- 修复后仅补测第一案：/tmp/task-17-production-browser-recheck-z2XIaz。1passed，测试10.3秒/总17.7秒。未重复第二案35秒离线等待。不声称同一轮2全绿。
- 汇总索引：/tmp/task-17-production-browser-evidence.json。

最终第一案：20次真实键盘input捕获到requestAnimationFrame，P95 12.7ms/max13.2ms，不含Playwright往返；当前代表页面199个DOM元素、Run18条SQL事件。普通终态created_at到最新状态DOM436ms（单样本且包含提交时间，不是P95负载指标）。首次路由只加载AgentTaskView视图chunk，进入编辑/岗位页才加载其view chunk。严格CSP下pageErrors=[]、cspViolations=[]。真实上传解析成功、12条SQL事件、原件保存和向量入库结果齐全；真实PDF81495bytes且签名%PDF-。见input-latency.json、normal-run.json、upload-result.json、production-security-and-routes.json、production-resume.pdf。原首案输入P9513.8ms/max16ms、正常事件457ms保留在首次目录，未覆盖。

第二案使用首轮通过证据：实际离线35125ms，失败请求间隔约1/2/4/8/15秒，确实进入最长退避；online到最新succeeded DOM33ms（浏览器performance时钟）。从after=7恢复且只有一条新SSE；继续观察15100ms没有旧计时器重复连接。未提交回答保留，恢复后明确提示已处理但保留本地输入。CSP/pageerror均0。原始offline-recovery.json、trace/video在首轮第二案目录。

## 首轮失败与修复因果

首案upload Run 0f2d7e9f-4a4f-4c8c-ad36-37adbeaf6727实际failed，errorCode=document_parse_failed、result=null、lastSeq=6。trace提取27个无凭据合成快照响应，保存首次目录failed-upload-responses.json。原trace没有完整SSE body，未声称已取回该Run所有SQL事件；补测成功Run已额外保存SQL事件。

确定上传根因：新生产Harness传http_client，旧backend/tests/e2e_legacy_fixture.py重复传同名参数，构造时TypeError。直接构造真实Harness RED：/tmp/task-17-browser-fixture-red.txt。测试夹具最小修为pop/close被替换的生产client后注入MockTransport(follow_redirects=False)，保留timeout/max_retries。GREEN：/tmp/task-17-browser-fixture-green.txt；脚本/tmp/task-17-browser-fixture-check.py。没有供应商请求。

同时发现独立生产退出错误：daemon读sys.stdin.buffer，正常main返回时可发生BufferedReader锁fatal。B按raw os.read修复并真实normal child/父SIGKILL双库4绿，日志/tmp/task-18-document-exit-{red,green}.txt。finish_run只改RUNNING、不会将SUCCEEDED降级，这段已正确；没有把fatal错误当成上传失败唯一根因。

## 实际截图检查

两轮共16张截图逐张通过view_image查看；清单写在汇总JSON中，每张viewed=true。每轮首案各7张：waiting-long-answer的1440/390/320，completed-long-material的1440/390/320，answer-validation-error-320。首轮第二案另offline-max-backoff-390和online-latest-result-1440。无横溢、遮挡或按钮消失，长回答/引用自然换行，320错误提示和继续按钮可见。DOM横宽断言与实际看图均完成。代表页面未表现出虚拟化需求，未新增虚拟列表；没有声称浏览器已渲染单Run5万事件。

## 运行与清理

先 npm --prefix frontend run build，再 npx playwright test --config playwright.production.config.ts。RESUMATE_E2E_ROOT使用新独立目录，默认mkdtemp；本地另设置RESUMATE_E2E_NGINX_IMAGE=public.ecr.aws/docker/library/nginx:stable-alpine，CI默认官方nginx:stable-alpine。Linux tests-only runner添加--add-host host.docker.internal:host-gateway，Mac保持原Docker Desktop映射；Linux分支语法检查通过，未冒称本机做过Linux浏览器执行。默认playwright.config.ts明确排除生产案，普通列表仍31案/10文件，独立生产2案。

两轮完成后lsof检查4273/4274/8999/4373无LISTEN（exit1空输出），已通知root启动普通套件。此后root普通套件因独立Docker构建ENOSPC中断，不属于本生产浏览器结果。ENOSPC使本报告初次落盘失败，原始证据已在此前完整保存；空间恢复后补写本报告，未重跑或改写原始结果。
