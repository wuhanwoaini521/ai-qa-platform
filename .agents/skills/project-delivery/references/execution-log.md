# Execution Log

执行留痕的目的是**工程可审计**，不是记录模型脑内过程。日志本身是仓库写操作，只适用于真实交付任务且用户授权了相应修改。

## 只读边界

纯分析、解释、建议、只读 review 或"只给计划"不属于写入型 delivery run：不得创建 `.ai-runs/`、计划文件或任何其他仓库产物，也不得调用 `scripts/init_run_log.py`。即使用户显式调用 `project-delivery`，只读要求仍然优先。分析或计划直接写在回复中。

对授权的代码/配置/文档修改任务，先完成 repository understanding、分类和范围确认，再创建日志。不要为了准备记录而提前创建目录；任务最终取消或未获授权时不留空 run。

## 记什么 / 不记什么

记：

- 观察（读了什么、看到什么）
- 决策（选了什么方案、为什么、放弃了什么）
- 证据（命令、输出摘要、截图路径、文件行号）
- 改动文件清单
- 测试命令与结果
- review 发现与对应修复
- 遗留风险

不记：

- 模型的隐式推理过程、hidden reasoning、逐 token 推理链。
- "我本来想……"这类与交付无关的内心活动。
- 未脱敏的秘密。

日志是给未来的自己和同事看的工程记录。

## 目录结构

```text
.ai-runs/
└── 2026-09-29-history-redesign/
    ├── 00-request.md
    ├── 01-analysis.md
    ├── 02-plan.md
    ├── 03-implementation.md
    ├── 04-functional-test.md
    ├── 05-ui-review.md
    ├── 06-code-review.md
    ├── 07-fixes.md
    ├── 08-regression.md
    └── 09-final-report.md
```

文件**按任务类型动态生成**：后端 bug 修复不会有 `05-ui-review.md`。目录与骨架由脚本创建：

```bash
python scripts/init_run_log.py --task-type ui-redesign --title "history redesign"
python scripts/init_run_log.py --task-type bug-fix --title "pagination fails on page 3" --scale small
python scripts/init_run_log.py --task-type refactor --title "extract billing module" --dry-run
```

- `--task-type`：六类任务之一，决定生成哪些日志文件。
- `--scale small`：只生成 `00-request.md`、`01-analysis.md`、`09-final-report.md`。
- `--single-file`：只生成一个 `run.md`，适合极小任务且用户不要求持久留痕。
- `--date YYYY-MM-DD`：仅用于测试与需要固定日期的场景。
- `--runs-dir`：默认 `.ai-runs`。

脚本只做确定性的文件系统准备，**不写业务内容或测试结果**。生成的空阶段文件不能预填"tests passed"、"review passed"等未发生的结果。

## 命名规则

```text
YYYY-MM-DD-<slug>
```

- slug 来自任务标题：小写、非字母数字转连字符、折叠重复连字符、去掉首尾连字符。
- 同一天重复：**绝不覆盖**，自动追加 `-2`、`-3`……
- slug 为空时用任务类型兜底，例如 `2026-09-29-bug-fix`。
- 非 ASCII 标题只保留其中的 ASCII 片段（`History 页面重新设计` → `history`），保证目录名始终可用。

## 留痕强度

| 规模 | 判定 | 留痕 |
| --- | --- | --- |
| small | 单文件、行为局部、无设计决策 | `00-request.md`、`01-analysis.md`、`09-final-report.md` |
| standard | 默认 | 按任务类型的完整阶段集 |
| large | 跨模块 / 跨页面 / 迁移 | 完整阶段集 + milestone 状态记录（写进 `02-plan.md` 与 `09-final-report.md`） |

极小任务（改一个 typo、调整一句文案）且用户没有要求持久记录时，允许只用一个 `run.md`。

中大型任务必须使用结构化日志。

## 文件字段

### `00-request.md`

原始请求、解析后的范围、任务类型、规模、仓库、分支、初始 `git status`。

### `01-analysis.md`

当前架构、相关文件、观察到的问题、约束、依赖、风险、假设。

### `02-plan.md`

实施步骤、预期改动文件、测试策略、review 策略、验收标准。

### `03-implementation.md`

改动文件清单、关键实现决策、新增组件 / 模块 / 函数、行为变化、执行过的命令。

### `04-functional-test.md`

跑过的测试、命令、结果、手工验证、发现的失败。

### `05-ui-review.md`

仅 UI 任务：视口、截图 / 视觉观察、P0、P1、P2、修复建议、review 结论。

### `06-code-review.md`

正确性、可维护性、复杂度、重复、错误处理、兼容性、测试覆盖、问题清单。

### `07-fixes.md`

review 或测试发现的问题、对应修复、涉及文件、验证方式。

### `08-regression.md`

回归覆盖范围、关键流程、结果、发现的回归。

### `09-final-report.md`

总结、完成项、实际验证、review 结论、遗留风险、`git status`、验收结论（`PASS` / `PARTIAL` / `FAIL`）。

## 脱敏

命令里涉及凭据时必须 redact：

```text
TOKEN=***
PASSWORD=*** --password ***
```

禁止把 secret 写进任何日志文件。

## `.ai-runs/` 的 git 策略

**不自动决定**入库还是忽略，也不自动改 `.gitignore`。

对实际交付任务首次使用本 skill 时：

1. 检查该项目的 `.gitignore` 与仓库约定是否已经提到 `.ai-runs/`。
2. 没有规则时，不擅自改 `.gitignore`；在 `09-final-report.md` 提醒日志位置，并将是否纳入版本控制留给仓库约定或用户决定。

只读任务不进入本节流程，因此不会产生该提醒所需的 run 文件。
