# 最终本机预览与实际截图

2026-10-30启动的最终预览：[岗位中心](http://127.0.0.1:4175/jobs)。合成账号 `browser-fixture`，密码 `synthetic-browser-password`。外部模型为确定性测试实现，不消耗供应商额度。

[原始运行报告](run-report.md)、[启动元数据](preview.json)、[浏览器观察](browser-observations.json)保留当时的源码基线、未提交状态和临时路径；后续提交不改写历史运行来源。本目录是稳定归档，原报告中的绝对路径仅说明现场位置。SQL、checkpoint、令牌及完整服务日志不复制到本目录。

四张截图均已实际打开检查，保留既定米棕视觉语言：

- [桌面岗位页，1440宽](screenshots/jobs-1440.png)
- [手机岗位页，390宽](screenshots/jobs-390.png)
- [窄屏岗位页，320宽](screenshots/jobs-320.png)
- [真实待补问任务，390宽](screenshots/waiting-input-390.png)

无横向溢出，浏览器页面错误为0；待补问任务通过真实worker执行到暂停点，截图时回答为空。未录制视频、未追加T20验收。该启动与视觉观察不替代之前已记录的完整或定向测试。
