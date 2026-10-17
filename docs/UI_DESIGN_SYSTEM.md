# Web UI 设计系统约定

本文件记录 ai-qa-platform 前端的共享视觉与交互规则，供后续页面新增与维护复用。当前 UI 使用
React + TypeScript + Vite，不依赖 Tailwind。**新增页面/组件先复用这里的 token、布局原语与状态
规则，再考虑新增样式。**

设计方向：**Modern Developer Tool + Enterprise SaaS + AI-Native IDE**——专业、克制、信息层级
清晰，像一个工作台，而不是一个后台管理系统的卡片墙。

## 视觉基线

- 页面保持浅色 QA SaaS 风格：浅灰蓝画布、白色内容面板、深色正文、靛蓝主操作；绿色/琥珀/玫瑰色只表达成功、警告、失败等语义。
- App Shell（导航、顶栏、Studio 全屏框架）维持现有导航结构与设计 token；页面内容通过共享页面组件建立层级。
- 阴影、渐变和高饱和装饰用于层级提示，不替代正文对比度或状态文字。

## 设计 Tokens

单一来源：所有 token 只在 `apps/web/src/index.css` 的 `:root` 中声明一次，其余 CSS 文件只能
`var(--token)` 引用，不得写死颜色/字体/间距。

### 颜色

| 用途 | Token | 当前基准 |
| --- | --- | --- |
| 页面画布 | `--canvas` / `--bg-app` | `#f5f7fc` |
| 面板表面 | `--surface` `--surface-raised` `--surface-inset` / `--bg-card` | `#ffffff` |
| 正文 | `--ink` / `--text-main` / `--ui-ink` | `#14162b` |
| 次级正文 | `--ink-soft` `--ink-muted` / `--text-muted` | `#68708a` / `#626b80` |
| 分隔线 | `--line` `--line-strong` / `--border-color` | `#e3e7f2` / `#e7eaf5` |
| 品牌主色 | `--accent-blue` / `--primary` | `#4f46e5` / `#6366f1` |
| 聚焦轮廓 | `--ui-focus` | `rgba(99, 102, 241, 0.32)` |
| 成功/警告/失败/AI | `--accent-green` `--accent-amber` `--accent-red` `--accent-violet` | 仅用于对应状态 |
| 圆角阶梯 | `--r-xs` `--r-sm` `--r-card` `--r-lg` `--r-pill` | 输入、小面板、卡片、主容器 |
| 间距阶梯 | `--sp-1` … `--sp-7` | 4/8/12/16/24/32…（不要随手 9px/11px） |
| 尺寸骨架 | `--sidebar-w` `--toolbar-h` | 侧栏与顶栏 |
| 动效 | `--dur` `--ease` | 只用于反馈与空间变化 |

旧变量（如 `--color-primary`、`--surface-primary`、`--ui-*` 别名族）作为兼容层保留在 `:root`。
新增样式优先使用语义 token；迁移旧页面时再逐步删去别名，避免一次性改动破坏功能页面。

### 状态颜色语义（不要混用）

| 语义 | token |
| --- | --- |
| 通过 / 已验证 / 已连接 | `--accent-green`（文本 `--ui-success-strong`） |
| 运行中 / 处理中 / 分析中 | `--accent-blue`（AI 相关用 `--accent-violet`） |
| 待处理 / 不稳定 / 需确认 | `--accent-amber`（文本 `--ui-warning-strong`） |
| 失败 / 阻断 / 危险操作 | `--accent-red`（文本 `--danger-text`） |
| 中性 / 未执行 | `--ink-muted` + `--line` |

### 字体

`--font-sans` 与 `--font-mono` 使用**本地与系统字体栈**：应用不请求任何外部字体 CDN
（`apps/web/index.html` 中已无任何外链资源）。原因是离线/内网环境必须正常渲染，且被拦截的
webfont 会让 `document.fonts.ready` 永不 resolve，从而挂住 Playwright 截图。需要商用字体时，
把字体文件自托管到 `apps/web/public/fonts/` 并在 `src/index.css` 用 `@font-face` 声明。

字号取 `--fs-xs`/`--fs-sm`/`--fs-label`/`--fs-body` 等既有阶梯；代码、ID、locator、计数一律用
`--font-mono`（含 JSX 内联样式，禁止 `fontFamily: 'monospace'` 这类临时写法）。

### 圆角、阴影、间距

- 圆角使用 `--ui-r-xs`、`--ui-r-sm`、`--ui-r-md`、`--ui-r-lg`，分别适用于输入控件、小面板、卡片和主要容器。
- 阴影使用 `--ui-shadow-xs/sm/md/lg`。普通数据卡片以轻阴影和边框为主。
- 间距使用 `--sp-1` 至 `--sp-6`（4、8、12、16、24、32px）。页面主内容默认 24px 间距，窄屏收至 10–14px。

## 布局原语

- 应用外壳：`--sidebar-w` 侧边导航 + `--toolbar-h` 顶部工具栏；滚动只发生在内容区
  （`.workspace-main-scroll` 等显式滚动容器），避免 3–4 层嵌套滚动。
- QA 工作台网格：`.workspace-grid`（左资源区 / 中工作区 / 右上下文面板 / 底部 dock）。尺寸决策
  集中在纯函数 `apps/web/src/features/workspace/workspaceLayoutModel.ts`（断点 820 / 1280，窄屏
  时上下文面板转为抽屉）。**布局判断写在模型里，不写在 CSS 魔法数里。**
- 底部执行区（run / results / browser / debug）是一个可折叠、可调整高度的 dock，折叠时不得重新
  挂载内容，避免丢失运行状态、浏览器会话与滚动位置。
- 面板缩放统一用 `apps/web/src/features/workspace/usePaneResize.ts`（指针拖拽 + 方向键 + Home/End +
  `role="separator"` + localStorage 记忆）。新面板不要再手写 pointermove 监听。
- 高度不要写 `calc(100dvh - 300px)` 这类固定魔法数；用 flex 填充 + 可折叠面板表达。

## 共享组件

- 页面容器与标题：`.page-container`、`.page-header`、`.subtitle`
- 指标：`.stats-grid`、`.stat-card`、`.stat-value`
- 面板、表单和按钮：`.card`、`.form-control`、`.btn`、`.btn-primary`、`.btn-secondary`
- 状态：`.status-pill` 与 `success/running/warning/failed` 等语义修饰类；状态必须同时保留文字，不能只靠颜色表达。
- Tabs 与宽表：`.tab-btn`、`.table-responsive`。宽表放进 `.table-responsive`，让横向滚动留在表格容器，不扩大页面视口。
- 异步状态与反馈：`.async-state`、`.alert` 及 `alert-error/warning/info` 修饰类。
- 旧页面兼容基础：低特异性的 `:where(button/input/select/textarea)` 规则兜底；更具体组件类应覆盖它，避免重复造基础控件。

### 组件规则

- 同一模式（时间线、日志查看器、失败面板、覆盖地图）只允许一个实现；新增前先在
  `apps/web/src/components/` 中找现成组件。
- 每个数据区域必须有四态：**loading / empty / error / ready**。空态给出下一步动作，错误态给出
  原因与重试入口，不要只留空白或一行英文异常。
- 进阶配置放进折叠区（`.qd-advanced`、`<details>`），但不要让用户为了发现核心操作而展开折叠。
- 所有耗时操作有进行中状态；破坏性操作有确认；只读执行有明确状态标签。
- 动画只表达“正在发生什么”和“空间变化”，不做装饰性渐变或无限扫描动画。

## 响应式规则

- `1050px`：统计卡片按可用宽度重排；多栏 Test Cases、Runs、Tasks 页面转为单栏；宽表使用容器内横向滚动。
- `760px`：页面头部堆叠，卡片与统计缩紧；Recorder 改为纵向工作区，绑定信息及设置单列显示。
- `520px`：App Header 改为上下两行，标题不得逐字竖排；侧栏切换为图标导航，菜单项保留 `aria-label` 与原生提示；操作按钮可换行，但标签和按钮文字不得被压成竖排。
- CSS Grid/Flex 子项默认加入 `min-width: 0`；长文件路径、节点 ID、错误消息允许断行。
- Recorder 另外在 1200px 与 1500px 调整工作区和步骤编辑列数。
- 工作台内部使用容器查询（`.workspace-main-scroll { container-type: inline-size }`）而不是视口宽度，
  因为工作台宽度还取决于侧栏与上下文面板是否展开。

## 导航与信息架构规则

- 核心链路（需求 → 用例 → 自动化 → 执行 → 结果 → 失败调试 → AI/Jev 修复 → 验证）必须在同一工作台
  上下文内完成，**不跳页、不重选项目/用例/运行**。
- 遗留入口（`/requirements`、`/test-cases`、`/projects/:id/studio`、`/recorder`、`/failures`、
  `/workspace/:id`）只做重定向，且必须保留上下文参数。
- 同一能力只允许一个主入口；跨页面重复的列表/统计要么删除，要么改为工作台内的面板。
- 侧边栏只放稳定的一级入口（概览、QA 工作台、项目管理、运行、质量洞察、平台、设置），其余通过
  工作台内的面板与命令面板（Ctrl/Cmd+K）到达。

## 可访问性与交互

- 所有可操作元素保留明确 `:focus-visible` 轮廓；键盘焦点不可仅靠颜色表达。
- 次级正文使用 `--ui-ink-muted`，在白色与页面画布上的对比度至少达到 4.5:1；Recorder 远程视图聚焦后按 `Shift + Esc` 可返回地址输入框。
- 尊重 `prefers-reduced-motion: reduce`，减少动画与平滑滚动。
- 语义错误使用 `role="alert"`；禁用动作说明原因；可展开日志和详情使用原生 `details/summary` 或等价键盘可访问控件。
- 表格状态、Worker 浏览器标签和负载应同时提供可读文本，不将颜色作为唯一信息。
- 自定义控件的语义：Tab 用 `role="tab"` + `aria-selected`，折叠用 `aria-expanded`，尺寸调整用
  `role="separator"` + `aria-valuenow/valuemin/valuemax` + 键盘方向键，拖拽必须有键盘等价路径。
- 不做正式 WCAG 认证声明；这里只覆盖可观察到的无障碍问题。

## 如何被强制（回归测试）

| 约束 | 强制手段 |
| --- | --- |
| 无外部资源、核心 token 存在、`var(--token)` 都能解析、字体只走 token | `apps/web/tests/design-system.test.mjs` |
| 工作台布局决策 | `apps/web/tests/workspace-layout-model.test.mjs` |
| 面板缩放模型 | `apps/web/tests/pane-resize.test.mjs` |
| 双语 key 一致、`t('literal')` 都能解析 | `uv run python scripts/i18n_check.py`（`scripts/task.py lint` 中执行） |
| 真实渲染与交互 | Playwright E2E（`apps/api/tests/*_e2e.py`）+ `.ai-runs/` 下的 Before/After 截图 |

修改 UI 后至少运行：`pnpm --filter @ai-qa/web test`、`pnpm --filter @ai-qa/web typecheck`、
`pnpm --filter @ai-qa/web build`、`cd apps/web && pnpm lint`。

## 新页面检查清单

1. 复用共享容器、卡片、表单、状态与异步组件，不复制 token 值或基础控件样式。
2. 页面局部颜色优先使用语义 token；状态标记同时显示文本。
3. Grid/Flex 内容设置 `min-width: 0`；宽表包在 `.table-responsive` 中。
4. 至少检查 1440×900、1920×1080；重点交互页另检查 390px 窄屏。
5. 页面空态、错误态、加载态和键盘焦点应与成功态同样清晰。
6. 新增文案同时写入 `en` 与 `zh-CN`，并用字面量 `t('key')` 引用，最后跑 `scripts/i18n_check.py`。
7. 提交前跑 `design-system.test.mjs` 与前端四条验证命令。

## 已知缺口（下一版优先级）

1. `apps/web/tests/` 只有模型/存储层的 node:test，**没有任何组件级 UI 回归测试**；工作台与页面改动
   只能靠浏览器 E2E + 截图人工核对，这是当前最大的结构性风险。
2. 工作台上下文栏与检查器抽屉仍有两处手写 resize 逻辑未迁移到 `usePaneResize`。
3. `apps/web/src/features/runtime/runtime.css` 仍有自己的变量命名空间与重复状态色，待并入统一语义色。
4. 侧边栏“运行”“质量洞察”与工作台内的结果/发现视图仍有重叠入口，需按上文继续收敛。
