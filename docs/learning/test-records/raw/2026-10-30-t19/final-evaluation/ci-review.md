# T19 CI 直接入口只读审查

2026-10-30；审查当前 `.github/workflows/ci.yml` 已启用作业直接调用的入口及依赖。只读源码与锁文件；未运行 GitHub Actions，也未重复已通过的测试。

结论：未发现这些入口存在 macOS 绝对路径或缺依赖造成 Linux 必然失败、无声跳过所承诺测试的问题。

- 普通与生产浏览器服务脚本优先 `shutil.which('docker')`，macOS 路径只是 fallback；生产 nginx 在 Linux 显式配置 `host-gateway`，API 监听 `0.0.0.0`。相对 `.venv/bin/python` 与 `uv sync` 的环境位置一致。
- Python 与 Node Playwright 锁定为同一 1.64.1，浏览器作业安装 Chromium 及 Linux 系统依赖；后端与浏览器均安装中文字体。后端测试安装 OCR extra；当前浏览器上传案例使用文本输入，不依赖未安装的 OCR extra。
- 扩展 Node 测试从 frontend 包解析 jsdom；该作业先执行 frontend `npm ci`，依赖来源完整。frontend 各命令均有对应脚本。
- 后端 MySQL fixture 支持 CI 传入的 URL；不依赖本机 socket，也不会因没有 socket 而跳过 MySQL 参数组。数据库特定的少量 skip 对应另一种数据库的已分开的行为。
- 四进程恢复由独立作业显式启用，使用刚构建的镜像与新 invocation context；不会把普通 stub 的四个未执行项算作通过。

范围边界：旧的 Redis 集成、delivery、PDF Compose 和 worker Compose opt-in 项并未在普通后端作业全部启用；本次 CI 实际定义的是普通后端、frontend、extension、26 案 stub、四恢复、实际浏览器及生产 nginx 作业。以上结论没有把未选择的专项或本地验证冒称为 CI 已执行，也不替代后续远程首跑。
