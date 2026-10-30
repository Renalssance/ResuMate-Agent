# T19 可归档交付证据

本目录仅包含本次实际执行的公开构建/测试证据与合成业务数据。不要将原始临时目录的 build.env 或项目 *.env 补入；8个随机JWT/MySQL配置文件已排除。没有复制用户预览或真实账户数据。archive-privacy.json记录已知实验secret和JWT输出检查均为0。

- build-attempts：四次独立构建的原始文本/JSON、执行脚本以及各次实际Dockerfile/Compose/锁文件。a5454d0f71是ENOSPC失败；1c9d135ffa是apt挂起主动终止；6738606881是执行器PATH失败；5cd2b8fd52后端成功，前端首次阈值停止保留在build.json，续前端成功单列frontend-retry.json。
- production-build-source：5cd2b8fd52实际完整构建源码。生产镜像没有backend源码bind覆盖；集成只挂测试目录注入确定性模型。
- integration/first-auth-fixture-failure：真实首轮依赖检查通过后，测试shell认证环境优先级引起401。
- integration/final-pass：修正测试环境后的91.96秒真实成功。executed-test_delivery_compose.py是实际GREEN driver，生产镜像没有重建；evidence.json记录SQL/checkpoint恢复前后；backup为纯合成mysql.sql、业务卷和checkpoint卷；PDF两页已实际查看；cleanup-verification确认自有项目容器与卷均0。
- tests：readiness的6RED→6GREEN，及两轮真实集成pytest日志。
- task-19-delivery-report.md：完整结果、边界、镜像精确ID、空间维修和权限说明。

备份脚本对真实业务运行时，SQL与卷可能含私有账户材料和BYOK，应私有保管；本目录的备份仅由固定合成fixture生成。source/.env.example为公开模板，可归档。
