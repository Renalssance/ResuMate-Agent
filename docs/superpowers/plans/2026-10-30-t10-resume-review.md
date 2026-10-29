# T10：逐项审阅、保存与确认

日期 2026-10-30，基线 `c4327de`。沿用总计划与已授权连续开发。T09 已交付固定输入和来源建议，508 后端/67 前端及真实浏览器通过；本单元补完用户审阅闭环。

## 业务决定

每个初始草稿包含固定基底与建议。用户对每条建议选择 accepted（使用建议）、rejected（保留原文）、edited（使用本人输入）或 pending（撤销决定）。原始 before/after/reason/fact_refs/id 保留，编辑内容独立存 editedText，明确显示为本人编辑。requires_input=true 的建议不能直接 accepted；可以 rejected 或由用户 edited 补充，回答不会自动写入 ProfileFact。

保存时服务端从 Run 快照的原简历重建独立版本 resume，并应用 accepted/edited；pending/rejected 保留 before。不能接受任意整份 structured_content 或改来源。原 Resume 永远不被本接口覆盖；确认后该版本不可原地修改。

## API

复用 GET /api/resume-versions/{id}。

PATCH /api/resume-versions/{id}：{expectedRevision,changes:[{id,status,editedText?}]}。changes 为全部建议 ID，每个恰好一次。只有 edited 必须给 editedText（允许明确清空字段），其他状态不携带该字段。服务保持原建议与来源，revision+1，以 id/user_id/status=draft/revision 的条件更新判断冲突，不能只靠 FOR UPDATE。过期或已确认返回 409；无权限404；非法决定422。Response 是完整最新版本。

POST /api/resume-versions/{id}/confirm：{expectedRevision}。必须所有建议已经 reviewed（没有 pending，且缺信息建议未直接接受），先保存再确认。用相同条件更新令 status=confirmed、revision+1；过期返回409，已确认且版本一致可返回已有结果。没有修改建议的草稿可直接确认。来源仍存历史；确认是本人审阅，不自动确认长期事实。

历史任意 content 草稿保持只读，提示重新准备材料以生成可逐条审阅的建议；不添加旧格式任意写旁路。不新增DDL。T11才导出和投递关联。

## 页面与本地状态

新增 /resume-versions/:versionId，材料卡可跳入「审阅与编辑」；已确认显示「查看已确认版本」。材料准备导航保持选中。页面使用已有暖色、边框、字体、间距，桌面建议与预览分栏，手机单列。复用 FactReference 展示真实来源。

store 保留 serverSnapshot、localDecisions 和加载代次，dirty 根据决策与保存基线比较。保存失败/409保留输入。冲突时可查看服务端最新版本，明确选择「使用服务器版本」或「将我的修改应用到最新版本」；后者仅重放与旧基线不同的本地决定（避免覆盖另一页未被本地改动的字段），仍需用户再次保存。服务端已确认时不允许应用或保存，只能保留可复制本地输入并查看冻结版本。

保存过程中允许继续输入时，不可用迟到响应覆盖新输入：记录提交时的本地决定，响应建立新基线，仅清除已保存部分；也可以在保存期间明确禁用编辑，但不能悄悄丢输入。切换版本/账号/离开后旧请求不可回填。路由离开与浏览器关闭对未保存修改提示，取消离开保留状态。成功保存显示 revision，确认仅在本地无未保存修改且所有建议已审阅时启用。

接受、拒绝、撤销、编辑都有语义化按钮/表单。手工编辑缺信息建议明确属于本人补充。预览只展示当前选择会形成的简历内容；confirm 后只读。旧资料提示沿用T09，不能隐式刷新基底。

## 实施与验证

后端代理负责 schema/service/route、SQLite/MySQL 并发与不可变测试。前端代理负责 store/api/components/view/router/artifact入口、组件交互与失败保留测试。父代理负责真实双页面并发、未保存离开、确认冻结与截图、教学记录。

测试检测接受/撤销的字段投影、缺信息禁止直接接受、手动编辑不改来源、不覆盖原Resume、同revision只有一个更新成功、已确认不可改、其他账户拒绝、409本地输入不丢。实际浏览器按两个页面读取同revision后先后保存，检查409与合并重放；确认后第三次编辑拒绝。桌面/手机、长文、缺信息、冲突、加载失败和确认态截图必须实际打开检查。
