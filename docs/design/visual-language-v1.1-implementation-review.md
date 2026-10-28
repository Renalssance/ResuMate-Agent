# 视觉语言 v1.1 实施与验收记录

2026-10-24。依据：[实施计划](../superpowers/plans/2026-10-24-visual-language-v1.1-frontend.md)、[视觉规范](./visual-language.md)。

复审更正：原验收的“不出现整页横滚”不足以证明视觉布局正确，漏掉了桌面菜单按钮撑满顶栏、文档状态挤成竖排、设置地址窄列撑高以及资料表单意外四栏。本次已针对这些问题修复共享样式和设置参数布局。下文保留首轮记录作为历史，不作为上述问题不存在的依据。

首轮代码优化已实施，网页关键交互与布局曾按下述范围验证。真实 Chrome 扩展扫描、选择、填入与设置持久化受扩展运行环境限制，尚未验证，因此不将整轮扩展验收标为完成。

保留原工作区已有改动，使用分支 `codex/visual-language-v1.1`；未自动提交、合并或推送，未新增依赖。未更改 API 协议、权限、匹配算法、日期计算或自动填表引擎。

## 任务状态

| 任务 | 实现 | 验证 |
| --- | --- | --- |
| T1 共享样式与状态 | 已实现 | 网页浏览器与相关检查通过 |
| T2 外壳导航 | 已实现 | 网页浏览器与相关检查通过 |
| T3 首页认证 | 已实现 | 网页浏览器与相关检查通过 |
| T4 文档详情进度 | 已实现 | 网页浏览器与相关检查通过 |
| T5 完整资料编辑 | 已实现 | 网页浏览器与相关检查通过 |
| T6 匹配试题 | 已实现 | 网页浏览器与相关检查通过 |
| T7 投递全流程 | 已实现 | 网页浏览器与相关检查通过 |
| T8 设置与介绍 | 已实现 | 网页浏览器与相关检查通过 |
| T9 插件侧栏 | 已实现 | 静态预览与现有测试通过；真实扩展未验证 |
| T10 交付记录 | 已实现 | 覆盖清单、证据与限制已记录；扩展运行验收待补 |

## 覆盖清单

网页源路径统一为 `frontend/src/`，插件路径为仓库根目录。每一行区分修改、符合规范保留与未挂载。截图均使用测试数据，不包含真实账号或密钥。

| 对象 | 实现或保留理由 | 验证结论 | 截图 |
| --- | --- | --- | --- |
| HomeView.vue · `/` | 保留 Milo 构图与资产；收敛图片、标签边界和手机标题；触控、键盘与设备限定悬停。 | 首页未登录/已登录 CTA、登录注册入口；双主题及三种宽度。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-home.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-home.png) |
| AuthView.vue · `/login` | 保留认证接口，补充表单忙碌与错误关联，控件使用最小高度。 | 失败保留输入、成功进入文档、已登录入口；三种宽度。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-login.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-login.png) |
| AuthView.vue · `/register` | 独立验证注册路由；确认密码错误就地反馈。 | 密码不一致、请求失败、成功跳转、已登录显示；三种宽度。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-register.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-register.png) |
| DocumentsView.vue | 保留四张统计卡；上传键盘焦点；文案去实现术语；文本取消在前，提交时锁定草稿；窄容器表格为条目；加载/失败/筛选空与真正空分开。 | 文件及文本提交、失败保留与成功清空、详情面板、刷新保留内容。队列单独返回每份文件结果。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| ProfileFieldsView.vue | 单一底部取消/保存；编辑时锁定简历；移除内部字段路径；短字段两栏、长字段通栏；复制独立命中区域；补齐初次加载与失败。 | 增教育/项目再取消、失败保留草稿、成功只更新所选简历；320px/200%。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-profile-fields.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-profile-fields.png) |
| MatchingView.vue | 配置末尾开始操作；保留多选高度；刷新局部忙碌与错误，结果不被替换；分析限阅读宽度。 | 匹配请求、任务文字、分数/证据/分析；刷新中与失败保持内容；320px/200%。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-matching.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-matching.png) |
| QuestionsView.vue | 配置随容器折行；历史窄于56rem在前；持久选中态不依赖悬停；移除内部方法文案。 | 题数3传入请求、生成进度、题目展开；历史刷新保留选择和题目；320px/200%。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-questions.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-questions.png) |
| ApplicationsView.vue | 六张概览与统计弹窗保留；取消先保存后且底行归属；备注/链接通栏；失败保留草稿与错误反馈；记录纵向布局；日历首次加载不假报空。 | 新增失败、编辑取消、状态失败/保存、日程创建、选日/完成、统计焦点、XLSX导出；320px/200%。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-applications.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-applications.png) |
| SettingsView.vue | 参数换行并直接展示完整非密钥值；Key固定掩码；地址通栏；取消在前；编辑期间刷新不覆盖草稿；统计失败不冒充0。 | 已配置/缺失/加载失败、编辑取消、保存失败与成功、空/有数据统计；320px/200%。最近调用保留局部横滚。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-settings.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-settings.png) |
| ExtensionView.vue / extensionContent.ts | 保留正确内容与下载地址、文件名；共享CSS修正摘要、步骤和长地址折行，无需改源文件。 | 双主题、三种宽度；下载链接配置未改，现有内容映射保留。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-extension.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-extension.png) |
| AppLayout.vue | 768/1200断点与248px侧栏；原生导航dialog；窄屏标题模型换行；按页面限制阅读宽度；系统偏好切换停止背景。 | Tab、Escape、焦点返回、切路由关闭、1199/1200释放模态/滚动；真实玻璃背景生命周期。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| BrandLogo.vue | 符合规范保留：已有主页链接与可访问名称正确；公共CSS补足命中尺寸、品牌不压缩。 | 首页、认证页三种宽度及键盘焦点。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-home.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-home.png) |
| DocumentDetailDrawer.vue | 原生dialog；560px/手机全宽；标题关闭可达；三个面板长文换行，正文实底。 | 原文、结构化结果、存储状态；Escape与返回触发按钮。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| DocumentParseTaskList.vue | 符合规范保留接口与真实步骤/百分比；共享CSS统一标题、步骤折行、错误和减少动态反馈。 | 文件/文本fixture任务与失败；任务文字独立于旋转图标。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| TaskProgress.vue | 符合规范保留真实任务与steps接口；和解析任务复用共享样式，不编造进度。 | 匹配及试题任务fixture完成、错误与处理中分支。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-matching.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-matching.png) |
| EmptyState.vue | 符合规范保留title/description接口；调用方负责区分空、过滤无结果、失败和初次加载。 | 七个工作台页面空/失败，六个取数页面初次忙碌；组件不承担错误反馈。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| EvidenceList.vue | 符合规范保留简单items接口；共享样式改为分隔线、长证据自然换行与48rem阅读宽度。 | 长证据与匹配分析、普通/追问题；空证据沿用父级提示。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-matching.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-matching.png) |
| CopyFieldButton.vue | 44px独立命中区，不盖输入；保留Clipboard和名称；成功与失败均有可见文字，失败提示手动复制。 | 真实组件测试成功/失败/值变更/空值；新增失败可见提示先红后绿；手机布局。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-profile-fields.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-profile-fields.png) |
| MiloStatusBubble.vue | 符合规范保留：单气泡、真实状态映射与live region；共享样式自然换行。 | 导航窄屏与200%放大；没有新增历史气泡或重复消息。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| StatusTag.vue | 提示完成显示“已完成（有提示）”；保持其他状态映射；状态色/文字层级统一。 | 文档fixture warning状态、存储布尔状态；文字可见而非只靠颜色。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| AgentStatusPanel.vue | 未挂载：审查并改为用户可读状态文案；历史滚动与间距保留，不重新接入页面。 | 仅静态审查；未将其声称为页面浏览器验证。 | 不适用 |
| App.vue / main.ts / router/index.ts / useResponsive.ts | 符合规范的公共/工作台分流、10路由与样式入口保留；AppLayout实际接入useResponsive判断导航断点。 | 10路由全部打开；767/768、1199/1200边界和桌面恢复。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-documents.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-documents.png) |
| styles/main.css / brand.css | 品牌变量/公共页由brand.css维护，工作台规则集中main.css；移除旧内容玻璃类与重复覆盖；无全局transition、装饰入场、信息卡悬浮；新增form-actions与容器折行。 | computed布局/焦点、两主题、coarse命中规则、减少动态、高对比；结构约束与生产构建通过。 | [桌面](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-1440-settings.png) / [手机](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/simple-390-settings.png) |
| frontend/index.html / frontend/style.css | 符合规范保留index的zh-CN；旧style.css未被应用入口引用，确认未使用后不盲改。 | 入口静态核对；生产构建验证真实引用。 | 不适用 |
| extension/sidepanel/sidepanel.html | 设置保存移到所属区域末尾，棕色主操作；后端地址通栏；所有ID与i18n绑定保留。 | 中英静态预览、320/390px与200%；真实Chrome扩展流程未验证。 | [中英窄屏](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/sidepanel-zh-320.png) |
| extension/sidepanel/sidepanel.css / sidepanel.js | 侧栏本地品牌变量、44px控件、12/20px圆角、长文换行、诊断局部滚动、底栏按真实高度留位；JS动态类已检查，JS无需修改。 | 认证/i18n两文件通过，JS语法通过；静态预览不等同实际扫描/填入。 | [中英窄屏](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/sidepanel-zh-320.png) |

## 检查及具体用途

| 检查 | 检测的失败与处理方式 | 结果 |
| --- | --- | --- |
| 改动前 `npm --prefix frontend test` | 建立类型/已有业务基线；若失败先区分既有问题。 | 通过 |
| 改动后 `npm --prefix frontend test` | 模板与类型错误、日程/分组/导出/资料等业务回归；失败修复对应模板或绑定。 | 通过 |
| `npm --prefix frontend run build` | 类型和生产 CSS/打包失败；曾发现空选择器，已移除并重建。 | 通过，无 CSS 语法警告 |
| `glassEffects.test.mjs` | 内容玻璃覆盖、无差别动效或无效选择器回流；保留背景层约束，旧嵌套玻璃断言由v1.1替代。 | 通过 |
| `appLayoutFluidBackground.test.mjs` | 背景挂载、主题存储、可访问开关与减少动态配置回归。 | 通过，原有效约束保留 |
| `applicationsReviewComments.test.mjs` | 分类筛选和统计装饰的既有约束回归。 | 通过，未删有效断言 |
| `node --test extension/tests/auth.test.mjs extension/tests/i18n.test.mjs` | 认证/文案键与绑定回归，失败修正相关标记。 | 2/2通过 |
| `node --check extension/sidepanel/sidepanel.js` | 侧栏脚本语法回归。 | 通过，JS未改 |
| Chrome 路由矩阵 | 整页横滚、控件和长文裁切；失败调整具体容器。 | 10路由 × 1440/1024/390px × 双主题，共60组通过 |
| Chrome 初次/空/失败/刷新 | 初次忙碌误报空、刷新消失/失去选择；失败修正状态分支。 | 6取数页面初次忙碌、7工作台路由空/失败、4列表/参数刷新通过 |
| Chrome 交互 | 草稿丢失、错误保存范围、焦点与背景锁未释放、请求绑定错误。 | 导航/详情/认证/资料/设置/上传/匹配/题数/投递/日历/导出通过 |
| Chrome 偏好与边界 | 断点切换残留模态、系统减少动态仍循环、放大后横滚。 | 767/768与1199/1200；6复杂页320px/200%；导航390px/200%；动态偏好、高对比通过 |
| 插件静态预览 | 长中英文、诊断和底栏撑宽或遮住末项；失败修正对应CSS。 | zh/en × 320/390px，另320px/200%通过；仅静态 |

## 行为回归证据

- 复制失败提示：真实组件用例先复现无可见说明，再验证成功/失败反馈和原Clipboard行为。
- 多文件队列：两份简历排队，第二份失败，同时提交的JD文本成功；先复现返回值缺失，再验证逐文件结果 `[true, false]` 与文本 `[true]`，不再混用其他任务状态。
- 资料：增加教育/项目、修改姓名后取消还原；保存失败保留输入和编辑态；成功请求只发到所选简历的 structured-data 接口。
- 设置：取消恢复持久参数；失败保留草稿；成功清空输入密钥；页面始终只展示固定掩码。
- 投递：新增失败保留、编辑取消、状态失败/保存、日程新增/完成、日历选日、统计弹窗焦点和XLSX下载均使用拦截fixture。
- 原生dialog验证Escape、Tab焦点限制、关闭返回、切路由关闭、调整桌面后释放模态与滚动。

## 验证状态与环境边界

- 首页和认证页没有业务列表，空数据/列表加载不适用；分别验证未登录与已登录。插件介绍为静态内容，页面请求处理中不适用。
- `AgentStatusPanel.vue` 未挂载，仅审查源代码；没有将其当作页面已验证。
- 玻璃模式的实际WebGL背景另在不减少动态的Chrome上下文中验证，包含偏好变更销毁/重建；矩阵截图使用减少动态以保持静态证据。
- 浏览器API全部由本地fixture拦截；验证前端请求、任务状态与布局，不代表真实模型服务、云数据库或真实招聘站点端到端已验收。
- 真实Chrome扩展连接、扫描预览、选择、填入禁用状态和设置持久化尚未验证。静态截图不能替代此项。未发送真实删除请求。

## 证据位置

[证据索引](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-v1.1/index.md)。65张截图、4份结果JSON及浏览器验收脚本保存在此独立产物目录；脚本依赖本机已有Chrome/Playwright和本地Vite测试服务。

## 实施判断

- 遵照计划在含未提交改动的原目录增量实施，未创建会遗漏未提交文件的新worktree。
- 复用已有品牌资产、系统字体、CSS变量、组件与原生dialog；未新增框架、字体或动效依赖。
- 共享样式去掉被替代的内容玻璃规则，普通信息卡不新增装饰入场；轮询/任务百分比沿用真实业务输入。
- 保留分支与工作区，集成/发布不属于本次自动操作。


## 2026-10-24 页面复审修复

本次仅修改 main.css 与 SettingsView.vue：提高移动菜单隐藏规则的优先级；表头及桌面状态列保持横排、增加行内垂直留白，可用内宽不足60rem时转条目；状态标签不再拉伸占满手机行；资料短字段明确两栏，窄容器单栏；API地址独占一行，参数卡不再被长地址拉高。

验证：生产构建通过；本地Chrome以拦截数据检查7个工作台页面 × 1440/1200/1024/390px × 两主题，共56组。断言菜单显隐、桌面标题位置、状态标签高度、地址宽度、资料栏数、页面横滚及手机导航开关。人工查看修复前后桌面与手机截图。首页及认证页也重新截图审视；未更改业务逻辑。

首轮将无横滚检查等同于视觉验收是不充分的，本次修复针对实际截图中的错误，不宣称真实后端或扩展端到端已通过。

[修复后文档页截图](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-repair/repair-simple-1440-documents.png) · [设置页截图](/Users/bono/.codex/visualizations/2026/10/24/01a16c0f-b3ff-7743-a943-ecf6f1e06dbf/visual-language-repair/repair-simple-1440-settings.png)。同目录保留28张截图及可运行回归脚本（依赖本机Playwright/Chrome，Vite端口5175，API为测试数据）。
