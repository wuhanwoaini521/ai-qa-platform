# 侧栏响应布局补充修复 — 2026-11-06

## 用户反馈与复现

用户在 932×1106 的总览页反馈侧栏头部堆叠、项目选择/收起/搜索排列混乱。上次验收只检查了展开状态，未覆盖折叠状态及跨断点切换；本记录纠正该验收缺口。

Playwright 1.62.0 真实复现：点击收起后 is-collapsed=true，但 aside 实际仍为 232px、头部 display:grid。证据：output/playwright/sidebar/before-collapsed-932.png。

## 根因与修改

- 旧 max-width:1150px 规则把侧栏头部切成网格；组件库 --sidebar-w 仍为232px，导致状态、宽度、控件显隐不一致。
- Workspace 宽窗口 compact-shell 另有固定 min-width:236px 和 flex-basis:236px。补查发现初次修复后该路由仍无法收窄；已一并修复。
- design-system.css：替换上次仅针对展开状态的局部补丁，在 >=761px 桌面范围统一使用现有持久化折叠状态控制布局。展开沿用库的232px；收起在侧栏局部设 --sidebar-w:72px，并明确覆盖 width/flex-basis/min-width/max-width。
- 展开头部横排；收起时 logo/展开按钮竖排居中，隐藏项目选择器及完整搜索框、显示单个搜索入口；统一导航图标、平台入口、语言切换位置。
- Navigation.tsx：给已有语言按钮添加 ds-sidebar-language 布局类，不更改业务事件、路由或存储逻辑。
- 仅修改桌面规则；不新增移动端设计、依赖或第二套导航状态。

## 实际验证

- 命令均以 rtk 执行并使用 mise；浏览器沿用项目 .venv 的 Playwright 1.62.0，脚本启动时断言版本，没有运行依赖安装。
- 浏览器：`mise exec -- uv --cache-dir runtime/uv-cache run --no-sync python output/playwright/sidebar-review.py`，最终退出0、51项检查、page_errors=[]。
- 九种宽度：761、800、932、991、1150、1151、1280、1440、1920；每种覆盖展开、收起、重新展开。标准尺寸使用1280×800、1440×900、1920×1080，用户尺寸932×1106。
- 检查实际宽度232/72px、控件上下左右包含关系、头部不重叠、搜索/项目选择显隐、主区域无横向溢出、aria-expanded。
- 覆盖折叠后刷新、跨1150/1151断点调整、搜索与Esc焦点恢复、Ctrl+K、折叠平台菜单；在932与1440宽度验证 Dashboard、Projects、Quality、Workspace Debug 的两种状态和项目菜单。
- `pnpm --filter @ai-qa/web exec node --experimental-strip-types --test --test-isolation=none tests/design-system.test.mjs tests/project-selection-model.test.mjs`：13/13、退出0。
- `pnpm --filter @ai-qa/web typecheck`：退出0。
- `pnpm --filter @ai-qa/web lint`：退出0。
- `mise exec -- python scripts/task.py build`：最终退出0，3687 modules、约1分钟；既有Monaco chunk体积提示保留。
- `git diff --check`：无报错。

## 第二遍审查与证据

串行重新阅读最终 diff、CSS优先级和截图；没有声称独立agent review。收起态尺寸约束覆盖 compact-shell 的更高优先级规则；所有新规则限定于设计系统桌面侧栏，没有新颜色或 !important。最后宽窗口特殊路由的问题已被检查发现并修复。

已人工查看展开/收起932px及收起1440px截图。最终JSON及截图在 output/playwright/sidebar/，包括 after-expanded-932.png、after-collapsed-932.png、after-collapsed-1440.png。

## 结果与边界

本次侧栏修复验收：PASS。没有未解决的范围内布局阻断；没有提交、推送或管理用户的开发服务。沿用此前修改与未跟踪文件。

不代表移动端或整个平台业务验收。`.pi/team/QUALITY_GATES.md` 的旧 Graphite 设计条款与当前 AGENTS.md 的 self-ui-style 方向不一致，本次按当前仓库指导与实际组件库实现保留 Cold Light Workspace，没有按旧文档重做主题。

## 后续提交授权

用户在以上验收完成后明确要求提交并推送代码。仅将本会话组件库升级、总览/侧栏修复及本次工程Markdown记录纳入提交，保留此前10个未跟踪目录；不提交截图、运行数据或本地浏览器脚本。远程fetch后main无新增提交。源代码自最终验证后未变，复用上述检查结果；实际提交和推送状态以Git记录为准。
