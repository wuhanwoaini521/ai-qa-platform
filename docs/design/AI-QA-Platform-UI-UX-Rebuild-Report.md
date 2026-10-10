# AI QA Platform UI/UX Rebuild Report

**验收日期：** 2026-10-10  
**验收状态：** UI/UX **PASS / HEALTHY**；真实 AI/Jev 端到端闭环 **PARTIAL**  
**范围：** 工作台、Quality Discovery、总览、Run Dock、移动导航与前端状态反馈。未修改后端、qa-core、BrowserRuntime、AI/Jev 配置或运行数据。

## 结论

产品现在以项目工作台承载日常 QA 主线：需求 → 发现/验证 → 功能与缺口 → 用例 → 自动化 → 运行 → 失败处理。关键上下文留在当前项目中，执行和失败入口可深链到具体记录；空、加载、失败和重试状态有明确反馈。

两位独立评审提出的问题均已关闭。最终复审没有发现本轮范围内的 P0、P1 或 P2。12 个产品只用于研究信息架构和交互；没有复制代码、图标、品牌或图片资产。

## 开源产品设计挖掘

| 产品与参考 | 提取的交互模式 | 许可证观察与使用边界 |
|---|---|---|
| [VS Code](https://code.visualstudio.com/docs/editing/getting-started/userinterface) | Activity rail、项目上下文、主编辑区与 Problems/Terminal 面板分层 | [MIT](https://github.com/microsoft/vscode/blob/main/LICENSE.txt)；仅借鉴工作台层级 |
| [Zed](https://zed.dev/docs/project-panel) | 文件与上下文双向定位、可收起侧面板 | [仓库含 GPL-3.0-or-later 与 Apache-2.0 组件](https://github.com/zed-industries/zed)；未复用代码或图标 |
| [n8n](https://docs.n8n.io/workflows/executions/all-executions/) | 运行历史与当前执行分离，步骤级状态检查 | [Sustainable Use / fair-code 条款及其他组件许可](https://github.com/n8n-io/n8n/blob/master/LICENSE.md)；只研究执行状态表达 |
| [Kestra](https://kestra.io/docs/ui/executions) | 单次执行详情串起状态、日志、输入输出和失败步骤 | [Apache-2.0](https://github.com/kestra-io/kestra/blob/develop/LICENSE)；用于 Run Timeline 参考 |
| [Sentry](https://docs.sentry.io/product/issues/issue-details/) | 先展示影响、频率、事件脉络，再按需下钻 | [FSL-1.1-Apache-2.0 Future License](https://github.com/getsentry/sentry/blob/master/LICENSE.md)；不复用实现与品牌 |
| [Grafana Explore](https://grafana.com/docs/grafana/latest/visualizations/explore/) | 查询结果与 Inspector 分区，原始信息按需展开 | [AGPL-3.0](https://github.com/grafana/grafana/blob/main/LICENSE)；仅借鉴面板组织 |
| [Langfuse](https://langfuse.com/docs/observability/best-practices) | Trace 中并列展示模型、工具调用、延迟、输出与证据 | [MIT 为主，`ee/` 有例外](https://github.com/langfuse/langfuse)；不展示思维链 |
| [Dify Workflows](https://www.dify.ai/workflows) | 当前执行节点、输入输出、日志与人工审核边界 | [修改版 Apache-2.0，含附加条件](https://github.com/langgenius/dify/blob/main/LICENSE)；只借鉴状态与审核模式 |
| [Plane](https://docs.plane.so/work-items/work-item-details) | Side peek 保留列表位置，活动记录按时间查看 | [AGPL-3.0-only 为主](https://github.com/makeplane/plane)；只借鉴上下文连续性 |
| [Hoppscotch](https://hoppscotch.io/) | Request、Collection、环境选择与结果保持在同一工作区 | [MIT](https://github.com/hoppscotch/hoppscotch/blob/main/LICENSE)；本轮只打开页面观察，未发送请求 |
| [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer) | 动作列表、截图时间线、DOM/Console/Network 联动 | [Apache-2.0](https://github.com/microsoft/playwright/blob/main/LICENSE)；使用本项目现有能力，未复制实现 |
| [Bruno](https://github.com/usebruno/bruno) | Collection 树与 Request/Response 结果同上下文 | [MIT](https://github.com/usebruno/bruno/blob/main/license)；只借鉴分区方式 |

## 形成的设计语言

- **Workspace first：** 项目工作台是需求、发现、用例、自动化和运行的主入口；全局导航保持精简。
- **上下文连续：** 项目和实体留在 Context Explorer；中心区聚焦当前任务；Inspector 承载属性、AI/Jev 和证据。
- **时间线优先：** 用户先看到当前步骤、进度、失败点和下一步；DOM、Network、原始日志和结构化数据按需查看。
- **事实与推断分开：** 展示 provider/model、置信度、状态和证据；不展示思维链。
- **减少卡片堆叠：** 重复实体使用表格、列表、分区、标签页与抽屉；图只在表达流程或因果关系时出现。
- **失败状态可恢复：** 空、加载、部分失败和重试都有不同文案及可执行入口；未知数据不冒充零结果。

## 本轮改进

### 工作台与 Quality Discovery

- 项目工作区标题直接标识当前项目，避免重复的泛化标题。
- Discovery 报告提供 Quality Map、缺口、功能与活动分区；地图支持搜索、筛选和按功能、风险或覆盖状态排序，失败和未覆盖项优先显现。
- 启动表单有清晰的 URL 校验、模式说明、安全动作提示和首轮空状态；窄内容区自动单列排版。
- Discovery 运行历史失败时不再伪装为空结果：显示重试，加载成功前禁用启动；历史成功、需求列表失败时单独提示，可粘贴需求继续。
- 轮询错误与其他操作错误分开；后续轮询成功或重新加载历史后清除过时错误。

### 总览与 Run Dock

- 总览首屏加入待处理队列：最近失败运行跳转到**对应 Run**，阻塞或执行中的任务打开对应任务。
- 统计接口失败时数字显示为“—”；任务接口失败、最近运行失败与真正的空列表分别呈现。重试期间保留错误提示和重试状态。
- 超长任务标题最多显示两行并保留完整 `title`，修复 320px 内容区的横向溢出。
- Run Dock 使用模态语义；打开后焦点进入弹窗，Tab/Shift+Tab 被限制在弹窗内，Esc 关闭，关闭后焦点返回打开按钮。
- 测试收集失败时隐藏上一次成功的测试行，避免用户误操作过期列表。
- 小屏主导航显示横向滚动条提示，较窄视口仍能发现并滚动到后续入口。

## 验收证据

### 浏览器

- 使用本机运行中的 `http://127.0.0.1:5173/` 做交互验证。
- **Discovery 故障路径：** 在浏览器会话中模拟运行历史请求 503，确认出现错误与重试、启动按钮禁用、空状态隐藏；恢复请求并点击重试后回到正常空态。没有创建或写入运行。
- **Dashboard 故障路径：** 模拟统计请求 503，确认指标显示“—”且任务源成功数据仍可见；恢复请求并重试后提示消失。
- **表单路径：** `ftp://invalid` 显示输入错误并禁用启动；`https://staging.example.com` 校验通过且启动可用。没有点击启动。
- **导航路径：** 点击总览失败项可打开精确 Run；阻塞任务可打开对应任务。
- **Run Dock 键盘：** `aria-modal="true"`；打开后焦点进入弹窗；`Shift+Tab` 循环到末项；按 `Esc` 后回到启动按钮。
- **响应式：** 390px 下 `documentElement` 宽度与视口均为 390px，内容区 `clientWidth=scrollWidth=382px`；320px 下 Dashboard 内容区 `clientWidth=scrollWidth=312px`，无页面横向溢出。导航在 320px 下通过内部横向滚动显示后续入口。
- 当前页面 Console Error 数量为 0。

### 静态检查与构建

- `pnpm --dir apps/web run typecheck`：通过。
- `pnpm --dir apps/web run lint`：通过。
- 前端 25 个测试文件、104 条用例：全部通过，逐文件在进程内执行。
- `pnpm --dir apps/web run build`：通过，Vite 转换 3,391 个模块。
- 批量 Node `--test` 启动因当前环境限制返回 `spawn EPERM`；改为逐文件的进程内执行后全部通过。构建有既存 Monaco 大块提示（`MonacoEditorPane` 约 4.03 MB，压缩前），不影响构建成功。

### 独立评审

- 第一位评审：B+，确认无 P0/P1，指出 Discovery 历史加载和 Dashboard 部分失败两个 P2；均已修复。
- 第二位评审：首轮要求改进，指出 Dashboard 未知值、重试反馈、Discovery 轮询错误、Studio 旧结果和移动导航问题；修复后复核发现最后 4 项边界状态，全部补齐。
- 第二位评审最终结论：**PASS / HEALTHY**；本轮范围内无剩余 P0/P1/P2。该复审为静态只读检查；交互行为由主验收浏览器验证。

## 截图索引

**改造前：** [总览](../../runtime/.design-research/before/home.png) · [工作台](../../runtime/.design-research/before/workspace.png) · [发现](../../runtime/.design-research/before/discovery.png) · [Quality Map](../../runtime/.design-research/before/quality-map.png) · [Studio](../../runtime/.design-research/before/studio.png) · [运行](../../runtime/.design-research/before/runs.png) · [失败](../../runtime/.design-research/before/failure.png) · [设置](../../runtime/.design-research/before/settings.png)

**改造后：** [总览桌面](../../runtime/.design-research/after/dashboard-desktop-final.png) · [总览 390px](../../runtime/.design-research/after/dashboard-mobile-390px-final.png) · [总览 320px 与导航滚动提示](../../runtime/.design-research/after/dashboard-mobile-320px.png) · [Discovery 桌面](../../runtime/.design-research/after/discovery-empty-desktop-final.png) · [Discovery 移动端](../../runtime/.design-research/after/discovery-empty-mobile-final.png) · [Quality Map](../../runtime/.design-research/after/quality-map-desktop.png) · [运行](../../runtime/.design-research/after/runs-desktop.png) · [失败桌面](../../runtime/.design-research/after/failure-desktop.png) · [失败移动端](../../runtime/.design-research/after/failure-mobile.png) · [Studio](../../runtime/.design-research/after/studio-desktop.png) · [设置](../../runtime/.design-research/after/settings-desktop.png)

参考页面截图保存在 `runtime/.design-research/references/`。研究和验收截图未混入产品运行时或提交产物。

## 限制与后续条件

- 当前 Settings 显示 AI `SIMULATION`、Jev `DISABLED`、Repair `DISABLED`；Discovery API 对 `proj_golden_shop_v1` 返回空运行列表。由于没有真实 AI/Jev 与可复核的 Discovery 运行，本轮不声称真实自动探索与报告链已验收，也没有启动任务来制造证据。
- 配置与密钥未改动，浏览器中的 503 是临时页面请求模拟，没有写入应用存储。
- Hoppscotch 外部页面的 Send 操作被自动审批拦截；仅观察客户端布局，未发送外部请求。

**最终判定：** 前端 UI/UX 重建通过；真实 AI/Jev 质量发现闭环待运行环境具备真实 provider、Jev 和数据后另行验收。

## 2026-10-10 末轮复核补充

- 总览最近任务限制为 8 条；390px 导航项宽度调整为 42px，浏览器实测文档宽度与视口均为 390px。
- Discovery 空输入 placeholder 改为明确的“例如：https://shop.example.com”；必填提示与 disabled 状态一致。独立复核最初提出的 placeholder 歧义 P2 已关闭。
- 独立终审：**B / Daily Use YES**；复核范围没有剩余已确认 P0/P1/P2。真实 AI/Jev Discovery 仍未验收；本轮未打开会自动触发 `collect/validate` POST 的 Automation Studio 阶段。
- 最新截图、DOM 状态、验证结果及审查限制见 [末轮验收记录](../../.ai-runs/2026-10-10-open-source-design-mining-ui-ux-rebuild/02-final-ui-acceptance.md)。

## 2026-10-10 第三轮：Inspector 与结果页收尾

**本轮判断：** Daily use **YES**；整体等级 **B**；UI/UX **PASS**。本轮没有剩余 P0–P2。真实 AI/Jev Discovery 闭环仍是 **PARTIAL**。

此前 Inspector 在 1440px 工作台中仍以遮罩对话框打开，挡住主区；结果页在桌面也强制使用抽屉。现在 1281px 及以上把 Inspector 放入工作网格右列，结果页沿用相同停靠方式；1280px 及以下再使用有遮罩的模态抽屉。拖动与方向键调宽使用同一组响应式夹值，separator 的实际宽度与 ARIA 范围一致。Inspector 标签使用 roving tab、方向键切换及显式 `tab`/`tabpanel` 关联；窄结果主区根据自身宽度切为两列或单列。

实现位于 [WorkspacePage.tsx](../../apps/web/src/features/workspace/WorkspacePage.tsx) 和 [workspace.css](../../apps/web/src/features/workspace/workspace.css)。本轮没有增加路由或复制参考产品的代码、图标、品牌与图片；没有改动后端、qa-core、Runtime、AI/Jev 配置或运行记录。

### 浏览器验收

| 实际视口 | Inspector 与结果区 | 无障碍与溢出结果 |
|---:|---|---|
| 320px | 模态抽屉 294px | `aria-valuemin/max/now=294`；页面宽度 320px，无横向溢出；打开焦点在关闭按钮 |
| 390px | 模态抽屉 358px | `min=300, max=now=358`；ArrowRight 后实际宽度与 `aria-valuenow` 同为 342px；方向键切至 AI 标签后 tabpanel 的 `aria-labelledby` 正确；Esc 关闭并把焦点还给“检查器”按钮 |
| 1280px | 模态抽屉 396px | `dialog`、`aria-modal=true`，焦点进入关闭按钮；页面无横向溢出 |
| 1282px（请求 1281px） | 结果页 docked，主区 518px | 结果内容自动单列；滚动宽度等于可用宽度 494px；页面无横向溢出 |
| 1440px | 结果页 docked，Inspector 396px、主区 700px | 结果内容自动两列；`clientWidth=scrollWidth=676px`，页面宽度 1440px |

当前页面重载后的 Console Error 为 0。网络记录只有页面数据读取与 Run 流的 stream-ticket 握手；没有触发 Run、AI、Jev、Repair 或 Discovery 写入操作。开发热更新早期曾短暂暴露一次声明顺序错误，代码修复并完整重载后复测通过。

### 两位独立评审

- 第一位评审初评给出 **B / Daily use YES**，曾指出断点、初始焦点和标签键盘行为问题；本轮终复核确认这些修复及结果容器断点均已落地，**P0–P2、P3 均无**。
- 第二位评审曾指出 Inspector 响应式宽度与 ARIA 不一致、桌面结果页仍是模态、结果页三列溢出；修复后再次复核，结论为**无剩余 P0–P2**。评审也记录了 P3：项目没有 Inspector 组件级自动化交互测试；本轮以真实浏览器断点与键盘交互完成验收，未为此引入新的测试框架。

### 第三轮截图

- **改造前：** [1440px Inspector 遮罩主区](../../runtime/.design-research/round-3/uiux-round3-before-inspector-1440.png)
- **改造后：** [1440px 工作台停靠](../../runtime/.design-research/round-3/uiux-round3-final-docked-1440.png) · [1440px 结果页停靠与两列内容](../../runtime/.design-research/round-3/uiux-round3-final-results-docked-1440.png) · [390px 模态抽屉](../../runtime/.design-research/round-3/uiux-round3-final-inspector-390.png)

### 本轮代码验收

- `pnpm --dir apps/web run typecheck`：通过。
- `pnpm --dir apps/web run lint`：通过。
- 前端 25 个测试文件、104 条用例：逐文件执行，全部通过。Node 测试运行器的并行子进程仍因环境限制报 `spawn EPERM`。
- `pnpm --dir apps/web run build`：通过，Vite 转换 3,392 个模块；保留既有 Monaco 大 chunk 提示（约 4.03 MB，压缩前）。
