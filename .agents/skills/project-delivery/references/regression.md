# Regression

回归范围由改动影响面和 `LOW` / `MEDIUM` / `HIGH` 风险决定，不是所有项目都跑同一套全量命令。先完成 targeted verification，再覆盖可能受间接影响的调用方和相邻行为。

| 改动 | 回归范围 |
| --- | --- |
| Bug fix | 已修路径、根因相关边界、同模块相邻入口。 |
| Shared component / public utility | 主要消费者与关键调用路径。 |
| API / contract | 所有相关调用方，以及旧调用方式和兼容行为。 |
| Persistence / migration | 正向路径、失败/回滚行为、旧数据读取。 |
| UI layout / shell / routing | 主要页面路由、关键交互和响应式视口。 |
| Dependency upgrade | 相关测试、lint/typecheck/build、API 和运行时兼容性；高风险升级扩大到完整套件。 |
| Config / CI / workflow | 受影响的本地命令、CI job 和生成/运行行为。 |

## 按风险扩展

- **LOW**：相关 targeted checks、直接调用方、改动 diff review。
- **MEDIUM**：针对性测试加相关 integration/caller checks；覆盖失败状态。
- **HIGH**：扩大到跨模块 integration、主要调用方和相关全量套件/CI jobs；确认兼容、数据和失败恢复路径。

UI 变更同时满足 `ui-review.md` 的浏览器和响应式门禁。若真实浏览器验证不可用，报告缺口并按 `final-acceptance.md` 决定 verdict。

纯文档/注释且无行为影响时可以不跑运行时回归，需说明理由。与改动无关的已有失败应标记为 `pre-existing`，不顺手修。

结果写入 `08-regression.md`：命令、覆盖路径、结果、未覆盖面和发现的回归。
