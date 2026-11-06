# dashboard-surface-layout

- run-date: 2026-11-06
- task-type: bug-fix
- scale: standard

## 结果

Dashboard 本次修复验收：PASS。

六处用户批注均已修复：标题/项目背景、主要悬浮卡片、执行轨迹全宽与元信息分行、工作流行对齐、项目区标题/按钮/列表间距。复查补充修复多行行动按钮高度和 991px 展开侧栏项目选择器挤压。

## 改动

- apps/web/src/pages/DashboardPage.tsx：官方 card 和 ghost 修饰类。
- apps/web/src/index.css：纠正 Dashboard 选择器与断点，恢复行布局，移除阴影清除覆盖并调整间距/内容高度。
- apps/web/src/design-system.css：紧凑桌面宽度下展开侧栏的行布局。
- apps/web/tests/design-system.test.mjs：同步此前用户确认的 v0.9.0 精确版本契约。
- docs/agent-handoff.md：本次交接。

## 证据

- 前端现有测试 317/317；最终受影响的契约/模型测试 12/12。
- 最终 lint、生产构建和 diff check 均退出 0；构建保留既有 Monaco chunk 提示。
- Playwright 1.62.0：四种桌面宽度、键盘执行证据入口、运行/工作流/项目跳转、Quality 返回、暗色 CSS、空/错误重试/加载，共 13 项；page_errors=[]。
- 代表性截图：output/playwright/dashboard/after-1440-top.png、after-991-runs.png、after-991-workflow.png、after-991-projects.png。
- 详细浏览器数据：output/playwright/dashboard/review.json。
- 串行 diff 第二遍审查完成，本范围未解决 P0/P1 为 0。

## 边界与遗留项

- 本次不代表全平台、移动端、所有业务流程或正式 WCAG 验收。使用真实本地数据验证展示/只读导航；没有触发执行或 AI 写入。
- 此前组件库升级的 package.json/锁文件/白名单改动及所有既有未跟踪目录均保留。
- 已知上游问题：v0.9.0 的开发依赖仍声明 @playwright/test ^1.64.1；本次 UI 修复未安装依赖，所有浏览器检查使用已安装的项目 Playwright 1.62.0。上游构建链的依赖政策问题未在本次 UI 范围内解决。
- 没有提交、推送或部署。没有停止用户的 5173 开发服务。
- 本次 .ai-runs 留痕不自动决定是否入库；.gitignore 没有统一忽略 .ai-runs，按仓库/用户约定处理。
