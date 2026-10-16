# UI/UX Audit — 真实浏览器验收

方式：Playwright 1.62.0（Python，`.venv`）真实 Chromium，headless，
在**真实项目上下文**（Golden Demo `proj_golden_shop_v1`，由 `/api/projects/golden-demo/seed` 播种）
下逐页导航，采集截图、控制台错误与三档宽度横向溢出。

脚本：`/tmp/ui_walk2.py`（无头 Chromium，先注入 `localStorage['ai-qa.auth-token']` 再导航）。
截图目录：`.ai-runs/enterprise-continuation/screenshots/`。

## 1. 页面逐项结果

| # | 页面 | 路由 | 结果 | 768/360 溢出 |
| --- | --- | --- | --- | --- |
| 1 | 项目列表 | `/projects` | ✅ | 无 |
| 2 | 项目总览 | `/projects/proj_golden_shop_v1` | ✅ | 无 |
| 3 | 需求分析 | `/projects/proj_golden_shop_v1/requirements` | ✅ | 无 |
| 4 | 测试用例 | `/projects/proj_golden_shop_v1/test-cases` | ✅ | 无 |
| 5 | 自动化 Studio | `/projects/proj_golden_shop_v1/studio` | ✅ | 无 |
| 6 | 工作台 | `/workspace/proj_golden_shop_v1` | ✅ | 无 |
| 7 | 执行记录 | `/runs` | ✅ | 无 |
| 8 | 质量度量 | `/quality` | ✅ | 无 |
| 9 | 失败与修复 | `/failures` | ✅ | 无 |
| 10 | 测试资产库 | `/library` | ✅ | 无 |
| 11 | 浏览器录制 | `/recorder` | ✅ | 无 |
| 12 | 系统设置 | `/settings` | ✅ | 无 |
| 13 | 失败修复工作流（专测） | 失败详情 → 诊断 | ✅ | 无（1440/768/360 均已断言） |

- **控制台错误：0**（`console.error` 与 `pageerror` 均为 0）
- **横向溢出：0**（`document.documentElement.scrollWidth <= innerWidth + 2` 在 1440 / 768 / 360 全部成立）
- 截图：`{page}-1440.png`（full_page）；失败页另有 `failure-ui/{desktop,tablet,mobile}.png`

## 2. 工作流信息架构

需求页与用例页共享统一的分阶段导航 `1 需求 → 2 发现 → 3 用例 → 4 自动化 → 5 结果`，
并共享「检查器 / 运行控制」侧栏 —— 即用户在同一上下文内向前推进，不需要跳页重找上下文。
本轮实测：`/requirements`、`/test-cases`、`/studio`、`/workspace`、`/failures` 均渲染该分阶段导航。

## 3. 本轮修复的 UI 级问题

| 问题 | 表现 | 修复 |
| --- | --- | --- |
| 顶栏长期误报「部分能力受限：常规 AI 运行健康」 | `/library`、`/recorder` 等页面顶部出现降级横条，但 AI 实际可用（真实 AI 验收刚刚通过） | 修复健康探针预算（后端），实测顶栏不再出现，`/api/ai/system-health` 由 `degraded` → `healthy` |

## 4. 未完成 / 已知 UI 问题

| 项 | 状态 | 说明 |
| --- | --- | --- |
| Studio 深度交互验收（编辑 → 运行 → 调试 → 证据 → AI 修复闭环） | 🔶 部分 | 页面加载与截图已完成；逐步交互未做 |
| Studio 首屏体积 | ⚠️ | `MonacoEditorPane` chunk 4.03 MB（gzip 1.04 MB），首次进入 Studio 需加载较大资源 |
| 图谱连线与节点布局（需求图 / 场景图 / 知识图） | 🔶 | 单元测试覆盖默认聚焦、搜索、fit；真实数据的视觉密度未逐张人工评估 |
| 暗色模式 / 主题 | 未测 | NOT RUN |

## 5. 结论

13 个目标页在真实数据下全部可用、无控制台错误、三档宽度无溢出，工作流上下文连续。
判定：**PASS（13 页渲染/响应式范围）**，Studio 深度交互与图谱视觉密度列为后续项。

## 6. D5 — Discovery Coverage Refresh

- 在真实项目路由 `/workspace/{projectId}?stage=discover&view=discover` 下，使用 Playwright 实际点击「刷新覆盖率」，成功反馈和 `VERIFIED` feature 行可见；真实 C 链之前已完成发现、真实 AI/Jev 生成、ACTIVE Playwright binding、browser TestRun PASSED。
- 1440 / 768 / 360 截图：`round-2/screenshots/discovery-coverage-before-refresh.png`、`discovery-coverage-after-refresh.png`、`discovery-coverage-tablet.png`、`discovery-coverage-mobile.png`。移动端表格在容器内横向滚动，页面整体无水平溢出。
- 一次历史 Playwright C-chain UI run 通过；后续加强直接断言 POST 200 / 无 API 错误 / per-run 截图路径后，尚未重新跑绿。另一次重跑在访问 UI 前被真实 AI 20s 超时阻断。不要将最新严格 harness 记为 PASS。
- 页面切换时清除旧 success/error feedback；按钮仅在终态 run 显示。多语言验收允许英文/简中标签。
