# 设计稿（pen.dev）

本目录保存 AI QA Platform 的高保真设计稿与其导出预览。设计稿不是实现来源，
`docs/UI_DESIGN_SYSTEM.md` 和 `apps/web/src/index.css` 的 `:root` 才是唯一权威。

## 内容

每个页面两种格式：`.png` 用于评审和文档引用，`.html` 是可交互的静态还原
（单文件，含内联 CSS）。

| 文件 | 说明 |
| --- | --- |
| `pen-design.pen` | 可编辑设计源文件（pen.dev schema v2.21，433 KB） |
| `exports/00-design-system.png/.html` | 设计系统封面：10 个核心 token 色板 + 布局/字体/状态语义规则 |
| `exports/01-dashboard.png/.html` | 平台总览（1480×900） |
| `exports/02-workspace-cases.png/.html` | QA 工作台 · 用例分析（1480×900） |
| `exports/03-workspace-results.png/.html` | QA 工作台 · 运行结果（1480×900） |

## 设计源文件

可编辑源文件：**`docs/design/pen-design.pen`**（433 KB，pen.dev schema v2.21）。

- 4 个顶层 frame、879 个节点、27 个文档变量，自包含（无 `imports`、无外部
  URL、无图片/SVG/脚本引用），可在任意机器上独立打开。
- 用 pen.dev 画布直接打开该文件即可继续编辑；保存后文件原地更新。
- 读取方式只有 pen.dev 画布或 pen.dev MCP 工具；不要用文本编辑器改动
  `.pen` 内容（它是加密/序列化格式）。

未保存到指定路径前，pen.dev 的默认文档目录
（`~/.pencil/documents/<uuid>/untitled.pen`）会保持 41 字节空壳，画布内容仅在应用
内存中。MCP `execute` API 没有“另存为”能力，只有 `Export`
（png/jpeg/webp/pdf/html-css/html-tailwind）——所以源文件必须在 pen.dev 应用中
手动 Save As 才能落到仓库。

顶层 frames 依次为：

- `00 · Design System — AI QA Platform`
- `01 · Dashboard — 平台总览`
- `02 · QA Workspace — 用例`
- `03 · QA Workspace — 运行结果`

> 导出 HTML 会引用 Google Fonts 的 Inter / JetBrains Mono。这只影响设计预览文件，
> 应用本体仍遵守 `UI_DESIGN_SYSTEM.md` 的“不请求外部字体 CDN”约束。

## 设计 token 绑定

画布中所有颜色都引用文档变量，变量值逐项来自 `apps/web/src/index.css`：

| 变量 | 值 | CSS token |
| --- | --- | --- |
| `$canvas` | `#f3f7fd` | `--canvas` |
| `$surface` | `#ffffff` | `--surface` |
| `$line` | `#e5ebf4` | `--line` |
| `$ink` | `#1c2942` | `--ink` |
| `$ink-soft` | `#40516f` | `--ink-soft` |
| `$ink-muted` | `#5d6b82` | `--ink-muted` |
| `$ink-faint` | `#8795aa` | `--ink-faint` |
| `$blue` | `#1d5bd7` | `--accent-blue` |
| `$green` | `#146c43` | `--accent-green` |
| `$amber` | `#805400` | `--accent-amber` |
| `$red` | `#b42333` | `--accent-red` |
| `$violet` | `#5d4bcf` | `--accent-violet` |

`*-soft` 与 `*-dot` 变体对应 CSS 中同名的 `--accent-*-soft`、`--accent-*-dot`。

## 与规范的一致性

设计稿刻意保留了 `UI_DESIGN_SYSTEM.md` 中的约束：

- 状态必须同时有文字（`CANCELLED` / `PASSED` / `未启动`），不用颜色单独表达。
- 卡片靠 1px 描边建立层级，不堆叠阴影。
- 每个数据区域有 loading / empty / error / ready 四态：运行结果页把“执行器尚未保存逐条测试结果”
  作为显式警告块呈现，而不是编造通过率。
- 字号只用 10 / 11 / 12 / 13 / 15 / 18 / 28 阶梯，ID、locator、计数一律等宽字体。

## 变更流程

设计稿是参考物，不驱动实现。若产品 UI 需要按此调整，走 `project-delivery` 流程：
先改 `apps/web/src/index.css` 的 token，再改组件，最后跑
`pnpm --filter @ai-qa/web test`、`typecheck`、`lint`、`build` 与 `scripts/i18n_check.py`。
