# T19 本轮公开验收证据

invocation `9ce4a722-d79a-42ee-b637-cef24946d6a5`。新镜像、固定当前源码、四次真实 SIGKILL；旧 T14 目录前缀不表示复用旧轮证据。

- `recovery/`：本轮 context/evidence、四案原始 SQL/图状态观察、命令与容器日志、实际挂载 backend 源码压缩包。四案均 executed/pass，pytest 452.92 秒。
- `evaluation/`：本轮30案 report/manifest/cases/calls、CLI原始日志、评测源码压缩包。CLI执行其余26案并合并上述四案，28.93 秒；该时间不是全部实际故障实验耗时。
- 原始 evidence 的绝对路径保留作溯源；归档内对应文件按相同 case ID 排列。运行数据库与原始 checkpoint 未复制。
- 只保存合成输入、公开模型输出与业务证据，没有 `.env`、供应商凭据或 JWT。没有供应商付费请求，live 语义质量仍 unreviewed。CI报告是源码只读结论，未声称 GitHub 远程执行。


## 执行版本与后续修复边界

本归档只证明 invocation `9ce4a722-d79a-42ee-b637-cef24946d6a5` 的实际执行版本：fresh 镜像 `resumate-t19-backend:5cd2b8fd52` 加四案开始前固定的 backend 源码挂载。`recovery/source-as-run.tar.gz` 与 `evaluation/source-as-run.tar.gz` 保留本轮实际源码，不随当前工作树后续修改更新。

本轮结束后正在修复的显式 HTTP client 生命周期 P2 不在这份执行源码中；后续新 backend 镜像及其验证应另行记录，不能用这次30案结果宣称后续修改已验证。root 的完整后端回归为1172 passed /19 skipped /286.60s，属于独立命令，也不能加进30案数量或混进上述两段耗时。
