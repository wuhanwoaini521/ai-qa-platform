# dashboard-surface-layout

- run-date: 2026-11-06
- task-type: bug-fix
- scale: standard

## 定位与风险

- 类型 bug-fix + UI review，MEDIUM：Dashboard 完整展示和共享侧栏局部样式；后端与业务逻辑不变。
- 已读 AGENTS.md、ROADMAP §0、UI_DESIGN_SYSTEM、agent-handoff、DashboardPage、相关全局/设计系统 CSS、组件库源码和现有测试。
- 总览的旧规则显式清除了卡片 box-shadow；标题/项目没有 ds-card。
- 执行轨迹和项目列表基础布局被限定在 is-compact-shell 且嵌套于 min-width:1151px；实际 Dashboard 仅有 is-dashboard-route。
- ds-btn 固定 height 叠加多行错误详情导致文字溢出；旧窄屏 rail 规则与展开的设计系统侧栏冲突。
- 真实登录本地应用并截图复现；截图与用户提供的六处问题一致。

## 验收边界

复用官方 ds-card、ds-btn-ghost；四种桌面宽度无横向溢出；轨迹/项目行撑满且元信息分行；多行行动文字包含于按钮；导航保留 project/run/nodeid；加载、空、错误重试可用。按仓库桌面产品约束不增加移动端验收。
