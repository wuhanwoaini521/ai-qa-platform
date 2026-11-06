# Web UI 设计系统约定

本文件记录 ai-qa-platform 前端的共享视觉与交互规则，供后续页面新增与维护复用。当前 UI 使用
React + TypeScript + Vite。**新增页面/组件优先复用 `@self/ui-style` 官方 token、`ds-*` 类和 React 控件；平台仅负责业务布局、语义别名与交互行为。**

设计方向：**self-ui-style Cold Light Workspace**——浅冷色点阵画布、紫色主操作与焦点强调、关键面板和控件采用凸起表面、方正小圆角。状态色继续表达通过、运行、警告、失败等既有语义。全系统共用同一视觉方向，包括 Dashboard 与 Workspace Debug/Explore；Graphite 只作为已被新方向取代的历史实现。

`@self/ui-style` 的通用控件规则与基础 token 是单一来源，应用现有语义变量在 `.app-design-system.ds-theme` 作用域内映射到包内 token。保留应用 `light` / `dark` / `system` 偏好；暗色使用同一组件规则和作用域内的暗色 token 映射，不再提供另一套 Graphite 视觉系统。移动端行为保持现状，本次不新增移动布局或移动验收。

## 视觉基线

- 默认桌面画布使用包内冷浅色 token（主表面 `#f7fafc`、柔和表面 `#eef3f8`、深层表面 `#e7eef6`）；全站点阵保持可见但低对比，不干扰内容。
- 主操作、选中态与键盘焦点使用紫色强调；通过、运行、警告、失败仍使用各自语义色并保留文字。
- 应用 Shell 与内容采用同一主题；保留现有左侧导航、顶部工具栏、内容滚动区和路由上下文。Dashboard/Workspace 的旧 route class 可继续表达布局，不得再提供 Graphite 配色例外。
- 运行状态胶囊只在 URL 明确带有 `runId` 时出现，读取现有 `useRunStore`，并返回到已有 Workspace 结果/失败面板；不推断“最近”或“最新”运行。
- 关键操作、指标和主要信息面板使用适度凸起层级；表格、日志、代码编辑器和工作台内嵌面板保持紧凑、连续，避免层层叠卡。
- `.app-design-system` 内的旧应用语义变量统一映射至包内 token；现存 `--graphite-*` 名称仅供尚未迁移的旧 route selector 兼容使用，必须在该作用域中直接映射到包 token，不得保留独立色值。新建或修改的组件不得引用这些兼容名；相关旧 selector 迁移后删除别名。

## 设计 Tokens

`apps/web/node_modules/@self/ui-style/src/tokens/tokens.css` 是当前固定版本的通用视觉来源，变量由 `.ds-theme` 限定。应用的 `--canvas`、`--surface`、`--ink`、`--line`、`--ui-*` 等兼容变量仅在 `.app-design-system` 内映射，不再把 `apps/web/src/index.css` 的旧 Warm Light/Graphite 色值当作第二来源。包版本由 `apps/web/package.json` 与 `pnpm-lock.yaml` 固定；不得虚构版本或复制包源码。

### 颜色

| 用途 | 包内 token | 当前基准 |
| --- | --- | --- |
| 页面主表面 | `--c-bg` | `#f7fafc` |
| 柔和/抬升表面 | `--c-bg-soft` | `#eef3f8` |
| 深层表面 | `--c-bg-deep` | `#e7eef6` |
| 正文/次级文字 | `--c-text` / `--c-text-strong` / `--c-text-muted` | `#333333` / `#26272b` / `#5b6370` |
| 分隔线/描边 | `--c-line` / `--c-stroke` | `#dde7f1` / 包内半透明描边 |
| 主操作/焦点 | `--c-accent` / `--c-accent-hover` / `--c-accent-active` / `--c-accent-ink` | `#6d5dfc` 系列 |
| 成功/警告/失败/信息 | `--c-success` / `--c-warn` / `--c-danger` / `--c-info` | 使用包内语义色，不混用 |
| 阴影 | `--sh-raised*` / `--sh-inset*` / `--sh-input*` | 包内双光源凸起/内凹层级 |
| 圆角 | `--r-xs` / `--r-sm` / `--r-md` / `--r-lg` / `--r-xl` | 6/8/10/12/16px |
| 间距 | `--sp-1` … `--sp-12` | 4/8/12/16/20/24/32/40/48px |
| 控件高度 | `--h-sm` / `--h-md` / `--h-lg` / `--h-xl` | 28/32/36/40px |
| 应用布局 | `--sidebar-w` / `--toolbar-h` / `--workspace-pad` | 保留现有布局尺寸，按业务布局语义映射 |

兼容变量只为未迁移调用方提供过渡映射；迁移完成后删除旧别名和旧控件样式，避免两套组件规则同时控制同一元素。


### 状态颜色语义（不要混用）

| 语义 | token |
| --- | --- |
| 通过 / 已验证 / 已连接 | `--c-success`（正文同时保留成功语义文字） |
| 运行中 / 处理中 / 分析中 | `--c-info`（AI 相关只在业务需要时使用 `--c-accent`） |
| 待处理 / 不稳定 / 需确认 | `--c-warn` |
| 失败 / 阻断 / 危险操作 | `--c-danger` |
| 中性 / 未执行 | `--c-text-muted` + `--c-line` |

### 字体

`--font-sans` 与 `--font-mono` 使用**本地与系统字体栈**：应用不请求任何外部字体 CDN
（`apps/web/index.html` 中已无任何外链资源）。原因是离线/内网环境必须正常渲染，且被拦截的
webfont 会让 `document.fonts.ready` 永不 resolve，从而挂住 Playwright 截图。需要商用字体时，
把字体文件自托管到 `apps/web/public/fonts/` 并在 `src/index.css` 用 `@font-face` 声明。

字号取 `--fs-xs`/`--fs-sm`/`--fs-label`/`--fs-body` 等既有阶梯；代码、ID、locator、计数一律用
`--font-mono`（含 JSX 内联样式，禁止 `fontFamily: 'monospace'` 这类临时写法）。

### 圆角、阴影、间距

- 通用尺寸、圆角、阴影从 `.ds-theme` 下的包 token 获取；应用只维护业务布局值与必要语义别名。
- 关键面板可用 `--sh-raised`，按钮/输入/选择控件用对应官方类及 `--sh-raised-xs` / `--sh-raised-hover-xs`；焦点环必须清晰可见。
- 表格、日志、代码编辑器、运行时间线与工作台内嵌窗格保持扁平紧凑，避免嵌套凸起卡片。
- 间距优先复用 `--sp-*` 包 token；工作区高度、dock 和面板尺寸仍由现有布局模型负责。


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

- 通用按钮、图标按钮、输入框、选择器、标签、卡片、基础表格、对话框和 Toast 优先使用包内 React 控件或官方 `.ds-*` 类；例如 `.ds-btn`, `.ds-input`, `.ds-select`, `.ds-card`, `.ds-badge`, `.ds-table`。
- 页面容器、工作区网格、指标布局、抽屉内部业务结构由平台负责，使用语义 token 和现有布局原语，不复制包内控件视觉规则。
- 状态由 `Badge`/`.ds-badge` 表达，但必须保留业务文字；过滤/排序仍使用原始 API 状态值。
- 业务表格继续使用现有列、排序、筛选、展开和虚拟化行为；包内 `Table` 只负责适合的语义骨架，不承担缺失的数据行为。
- 异步状态与反馈复用现有 `.async-state`、`.alert` 等交互实现；视觉可采用包内 `Alert`/`EmptyState`/`ErrorState`，不改变重试与错误恢复路径。
- 迁移中的旧 `.btn`、`.form-control`、`.card`、`.status-pill` 仅保留在尚未迁移的调用点，不得新增；每批移除对应旧规则，确保只有一个通用样式来源。

### 组件规则

- 同一模式（时间线、日志查看器、失败面板、覆盖地图）只允许一个实现；新增前先在
  `apps/web/src/components/` 中找现成组件。
- 每个数据区域必须有四态：**loading / empty / error / ready**。空态给出下一步动作，错误态给出
  原因与重试入口，不要只留空白或一行英文异常。
- 进阶配置放进折叠区（`.qd-advanced`、`<details>`），但不要让用户为了发现核心操作而展开折叠。
- 所有耗时操作有进行中状态；破坏性操作有确认；只读执行有明确状态标签。
- 动画只表达“正在发生什么”和“空间变化”，不做装饰性渐变或无限扫描动画。

### Round Six 页面模式

- Dashboard 使用全站 self-ui-style 画布与紫色主强调，保留执行概览、项目/需求/用例数量分区和可追踪状态文字；不再使用 Graphite 专属色板。
- Projects 使用紧凑注册表；加载失败与创建失败必须提供反馈，加载错误可重试；表格滚动限制在自身容器内。
- Quality 顶部五项指标共享 `.quality-metrics` 语义网格；评分方法使用原生 `<details>`；视图切换使用方向键可操作的 ARIA tabs。风险分数、覆盖计算、发布门禁和 AI/人工裁定均由既有业务服务负责，样式不得改变其含义。
- Explore 的任务步骤和 Debug 的代码/日志/运行面板在窄屏可切换；Task 面板需保留可见高度，长列表在面板内部滚动，不能压缩到 0px。

## 现有响应式规则（本任务仅维护，不扩展）

下面记录现有断点，供桌面布局避免溢出；本次验收只覆盖桌面基准视口，移动端仅保持既有行为，不新增移动专属设计或回归测试。

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
- 自定义控件的语义：Tab 用 `role="tablist"` / `role="tab"` / `role="tabpanel"` + `aria-selected` 和方向键导航，折叠用 `aria-expanded`，尺寸调整用
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
4. 至少检查桌面基准视口 1280×800、1440×900、1920×1080；移动行为保持现状，不在本任务新增移动验收。
5. 页面空态、错误态、加载态和键盘焦点应与成功态同样清晰。
6. 新增文案同时写入 `en` 与 `zh-CN`，并用字面量 `t('key')` 引用，最后跑 `scripts/i18n_check.py`。
7. 提交前跑 `design-system.test.mjs` 与前端四条验证命令。

## 已知缺口（下一版优先级）

1. `apps/web/tests/` 只有模型/存储层的 node:test，**没有任何组件级 UI 回归测试**；工作台与页面改动
   只能靠浏览器 E2E + 截图人工核对，这是当前最大的结构性风险。
2. 工作台上下文栏与检查器抽屉仍有两处手写 resize 逻辑未迁移到 `usePaneResize`。
3. `apps/web/src/features/runtime/runtime.css` 仍有自己的变量命名空间与重复状态色，待并入统一语义色。
4. 侧边栏“运行”“质量洞察”与工作台内的结果/发现视图仍有重叠入口，需按上文继续收敛。
