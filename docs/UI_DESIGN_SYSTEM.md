# Web UI 设计系统约定

本文件记录 `apps/web/src/index.css` 的共享视觉规则，供后续页面新增与维护复用。当前 UI 使用 React + TypeScript + Vite，不依赖 Tailwind。

## 视觉基线

- 页面保持浅色 QA SaaS 风格：浅灰蓝画布、白色内容面板、深色正文、靛蓝主操作；绿色/琥珀/玫瑰色只表达成功、警告、失败等语义。
- App Shell（导航、顶栏、Studio 全屏框架）维持现有导航结构与设计 token；页面内容通过共享页面组件建立层级。
- 阴影、渐变和高饱和装饰用于层级提示，不替代正文对比度或状态文字。

## 设计 Tokens

### 颜色

| 用途 | Token | 当前基准 |
| --- | --- | --- |
| 页面画布 | `--bg-app` | `#f5f7fc` |
| 面板表面 | `--bg-card` / `--ui-surface-solid` | `#ffffff` |
| 正文 | `--text-main` / `--ui-ink` | `#14162b` |
| 次级正文 | `--text-muted` / `--ui-ink-muted` | `#68708a` / `#626b80` |
| 分隔线 | `--border-color` / `--ui-line` | `#e3e7f2` / `#e7eaf5` |
| 品牌主色 | `--primary` / `--ui-primary` | `#4f46e5` / `#6366f1` |
| 聚焦轮廓 | `--ui-focus` | `rgba(99, 102, 241, 0.32)` |
| 成功/警告/失败 | `--success`, `--warning`, `--danger` | 仅用于对应状态 |

旧变量（如 `--color-primary`、`--surface-primary`）作为兼容别名保留。新增样式优先使用语义 token；迁移旧页面时再逐步删去别名，避免一次性改动破坏功能页面。

### 圆角、阴影、间距

- 圆角使用 `--ui-r-xs`、`--ui-r-sm`、`--ui-r-md`、`--ui-r-lg`，分别适用于输入控件、小面板、卡片和主要容器。
- 阴影使用 `--ui-shadow-xs/sm/md/lg`。普通数据卡片以轻阴影和边框为主。
- 间距使用 `--sp-1` 至 `--sp-6`（4、8、12、16、24、32px）。页面主内容默认 24px 间距，窄屏收至 10–14px。

## 共享组件

- 页面容器与标题：`.page-container`、`.page-header`、`.subtitle`
- 指标：`.stats-grid`、`.stat-card`、`.stat-value`
- 面板、表单和按钮：`.card`、`.form-control`、`.btn`、`.btn-primary`、`.btn-secondary`
- 状态：`.status-pill` 与 `success/running/warning/failed` 等语义修饰类；状态必须同时保留文字，不能只靠颜色表达。
- Tabs 与宽表：`.tab-btn`、`.table-responsive`。宽表放进 `.table-responsive`，让横向滚动留在表格容器，不扩大页面视口。
- 异步状态与反馈：`.async-state`、`.alert` 及 `alert-error/warning/info` 修饰类。
- 旧页面兼容基础：低特异性的 `:where(button/input/select/textarea)` 规则兜底；更具体组件类应覆盖它，避免重复造基础控件。

## 响应式规则

- `1050px`：统计卡片按可用宽度重排；多栏 Test Cases、Runs、Tasks 页面转为单栏；宽表使用容器内横向滚动。
- `760px`：页面头部堆叠，卡片与统计缩紧；Recorder 改为纵向工作区，绑定信息及设置单列显示。
- `520px`：App Header 改为上下两行，标题不得逐字竖排；侧栏切换为图标导航，菜单项保留 `aria-label` 与原生提示；操作按钮可换行，但标签和按钮文字不得被压成竖排。
- CSS Grid/Flex 子项默认加入 `min-width: 0`；长文件路径、节点 ID、错误消息允许断行。
- Recorder 另外在 1200px 与 1500px 调整工作区和步骤编辑列数。

## 可访问性与交互

- 所有可操作元素保留明确 `:focus-visible` 轮廓；键盘焦点不可仅靠颜色表达。
- 次级正文使用 `--ui-ink-muted`，在白色与页面画布上的对比度至少达到 4.5:1；Recorder 远程视图聚焦后按 `Shift + Esc` 可返回地址输入框。
- 尊重 `prefers-reduced-motion: reduce`，减少动画与平滑滚动。
- 语义错误使用 `role="alert"`；禁用动作说明原因；可展开日志和详情使用原生 `details/summary` 或等价键盘可访问控件。
- 表格状态、Worker 浏览器标签和负载应同时提供可读文本，不将颜色作为唯一信息。

## 新页面检查清单

1. 复用共享容器、卡片、表单、状态与异步组件，不复制 token 值或基础控件样式。
2. 页面局部颜色优先使用语义 token；状态标记同时显示文本。
3. Grid/Flex 内容设置 `min-width: 0`；宽表包在 `.table-responsive` 中。
4. 至少检查 1440×900、1920×1080；重点交互页另检查 390px 窄屏。
5. 页面空态、错误态、加载态和键盘焦点应与成功态同样清晰。
