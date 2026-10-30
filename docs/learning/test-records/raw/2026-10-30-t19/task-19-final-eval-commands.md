# T19 最终30案执行准备（尚未运行）

- 当前context：`/tmp/task-19-final-recovery-context.json`，从当前core的四个Compose ID/input逐字段写出，生成本轮新invocation。禁止借用旧证据。
- 等B fresh生产镜像成功、备份恢复结束明确交接后，使用其精确image tag。不存在成功tag时不得执行或换T20旧镜像抵扣。
- 本轮现有live补齐只做MockTransport/127.0.0.1；这条最终命令仍为stub，零供应商费用。

## 四个真实恢复

下面命令中的镜像值必须替换为B实际交付tag后才执行：

```sh
PYTHON_DOTENV_DISABLED=1 \
RESUMATE_COMPOSE_TEST=1 \
RESUMATE_RECOVERY_IMAGE='B提供的fresh生产镜像tag' \
RESUMATE_RECOVERY_CONTEXT=/tmp/task-19-final-recovery-context.json \
RESUMATE_RECOVERY_EVIDENCE=/tmp/task-19-final-recovery-evidence.json \
.venv/bin/python -m pytest backend/tests/test_agent_recovery.py -q -s \
  > /tmp/task-19-final-recovery.txt 2>&1
```

测试在开始前捕获一次完整当前backend；四案同快照、同context。每案独立Compose项目/卷，真实SIGKILL并记录ExitCode137、前后SQL/checkpoint/model_starts；只清自己项目。前三案等待正常90秒恢复窗口，不缩短产品门槛。首次失败日志和evidence需单独留档，再决定局部重试；不能以新文件覆盖历史失败后只报告成功。

## 最终全30案（只在双方eval代码与实际恢复证据冻结后执行一次）

```sh
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m evals.run \
  --suite core --mode stub --output /tmp/task-19-final-evals \
  --recovery-context /tmp/task-19-final-recovery-context.json \
  --recovery-evidence /tmp/task-19-final-recovery-evidence.json \
  > /tmp/task-19-final-evals.txt 2>&1
```

CLI会将manifest.invocation_id绑定context，并逐案验证input/id/invocation。预期（待实测）30执行且pass30，exit0；没有本轮四案证据则依既有门禁最多26执行/4not_run、exit2，不能把未运行写成pass。

报告读取 manifest/report、30份cases以及calls.jsonl，不仅引用pytest汇总。说明原12tailoring/8durable/6interview的实际SQL/graph路径，四恢复的SIGKILL/epoch/版本幂等证据；确定性stub不评价真实语义，真实live门禁仍未通过。所有实际执行日志、源码快照与context/evidence按实际路径归档，不生成hash。
