# 后端HTTP客户端修订镜像

在完整fresh验收过的resumate-t19-backend:5cd2b8fd52上COPY当前backend，得到resumate-t19-backend:7a3122655a-lifecycle。pyproject.toml、uv.lock、deploy/worker.Dockerfile与旧fresh源码逐文件直接比对一致，因此复用已经验证过的OS与Python依赖，没有重复安装。此为透明代码修订镜像，不冒充重新完整fresh构建。

修订Dockerfile、实际源码、build日志、image ID和命令已保存。新镜像内直接运行runtime-probe，无生产源码挂载；真实SDK与内存合成HTTP验证sync/async ×307/308 ×GC/显式close共8案全部通过，timeout7、SDK retries0、跳转目标零请求且每个transport只close一次。无供应商调用。旧fresh、中文PDF、就绪与备份恢复证据仍指向旧运行，不改写为新镜像重测。
