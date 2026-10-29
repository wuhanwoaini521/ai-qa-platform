# Failure Intelligence & Locator Repair (Human-Approved)

The Failure Intelligence system automates test failure taxonomy classification, sensitive data redaction, and human-in-the-loop locator healing.

## 可观测的多类型分析流程

失败详情通过 `POST /api/failures/{id}/analyze/stream` 输出实际执行事件；不是按定时器播放完成动画。流程依次读取测试与运行上下文、分析异常日志、检查类型对应的证据、调用 AI 分析根因、执行适用的 Locator 决策、整理建议，并等待真实复测。

| 失败类型 | 检查证据 | Locator 决策 |
|---|---|---|
| UI 自动化 | 已捕获的失败页面快照与候选元素 | 只有定位器错误且存在与失效目标关联的候选时执行 |
| API 测试 | 已捕获的 HTTP 日志、堆栈和测试源码 | 不适用 |
| Python 测试 | 异常堆栈与测试源码 | 不适用 |

`assert 1 == 2` 保持 `ASSERTION_FAILURE`，不能通过模型输出改成定位器错误。没有页面证据时显示“证据不足”，不会生成 `element → element` 等占位修复。上下文中的区域来自原始运行环境，未记录则明确显示未知；源码记录当前版本的 SHA-256，不能冒充失败发生时的源码。失败分析按项目和精确 pytest node id 查找唯一 ACTIVE Automation Binding，并将不超过 64 KB 的脱敏、按失败页 URL 匹配摘要及 binding/revision 引用纳入 Failure Evidence；完整历史保留在 Binding。Locator Repair 仅复用同页、录制时通过 Playwright 验证的候选，并在修复环境重新验证；证据不授权源码修改。

每一步保存状态、时间、耗时、脱敏证据和来源。模型事件记录实际 Provider / model；Fake 显示模拟，回退显示初步建议。Jev 失败后使用 Local Strategy 时记录回退原因，不能标为真实 Jev 选择。缺少真实 token 计数时记录未知。页面快照支持的 Locator 候选选择仍是未验证建议，不能表示实时页面已经验证。

## 回顾与实际验证

`GET /api/failures/{id}/analyses` 返回最近 20 次持久化分析。分析由服务端任务持有，客户端的事件流只是观察者：断流（关页、刷新）不会终止分析，重新连接会重放已持久化事件并继续跟随真实状态；只有显式 `POST /api/failures/{id}/analyses/{analysis_id}/cancel`（或界面上的“取消分析”）才真正停止模型调用并把记录置为 `CANCELLED`。每次分析的总预算由 `repair.analysis_timeout_seconds`（默认 300 秒）约束，超时保存为 `TIMEOUT` 并在修复行记 `ANALYSIS_TIMEOUT`；服务重启把遗留的运行中记录收敛为 `INTERRUPTED`，进程被强杀后由孤儿收敛（超出预算 + 宽限）按超时收尾。失败、取消、超时、中断都保留已有证据、给出可读原因，并允许重新发起分析（新尝试保留原始错误与时间线）。失败和中断保留已有证据，不显示未执行步骤已完成。历史可以在详情页面选择和展开查看。

分析任务目前由单个 API 进程持有，不是跨副本共享的持久化队列；多副本部署前必须先实现共享任务所有权与取消信号。定位器提案阶段会持续记录上下文、证据、隔离候选页和 Jev 决策进度，重复投递的同一事件只保存一次。源码变更仍须人工批准，模型不会直接写回项目代码。

“重跑测试用例”继承原运行环境、浏览器及 runner，并通过 `POST /api/failures/{id}/analyses/{analysis_id}/verification?run_id=...` 关联新复测。验证必须来自分析之后、同项目同 workspace、且精确运行该失败用例的新运行。只有运行及该用例的实际执行都为 `PASSED`，流程才显示验证通过。排队、运行中、跳过、失败、取消都不算通过。应用补丁显示“待复测”，不能仅凭写入代码宣称修复成功。通过复测仅证明该用例当前执行通过，业务语义仍需人工审查。

---

## 1. Failure Taxonomy Classification

Upon test failure, `FailureClassifier` analyzes pytest output and stack traces into structured categories:

| Category | Typical Signatures | Automatic Action |
|---|---|---|
| `LOCATOR_CHANGED` | `TimeoutError: waiting for locator(...)`, `Element not found` | Inspect captured evidence; propose a repair only when suitable candidates exist |
| `TIMING_ISSUE` | `TimeoutError: locator.to_be_visible() exceeded 5000ms`, `race condition` | Suggest explicit state waiting; retries require an explicit rerun policy |
| `ASSERTION_FAILURE` | `AssertionError: assert actual == expected` | Flag business logic regression |
| `ENVIRONMENT_ERROR` | `ConnectionRefusedError`, `502 Bad Gateway`, `Database error` | Flag infrastructure dependency outage |
| `UNKNOWN` | Unmatched stack trace pattern | Route to generic root-cause diagnosis |

---

## 2. Sensitive Data Redaction

Before failure artifacts and logs are persisted or passed to AI models, `SensitiveRedactor` strips confidential data:
- Passwords (`password: "***"`, `pwd=***`)
- Bearer tokens (`Bearer eyJ...` → `Bearer [REDACTED]`)
- API keys (`AKIA...`, `sk-live-...` → `[REDACTED_API_KEY]`)
- Private secrets and Authorization headers

---

## 3. Human-in-the-Loop Locator Repair Workflow

```text
[ Test Execution Fails with TimeoutError ]
                  ↓
[ FailureClassifier captures broken locator: "#old-btn-id" ]
                  ↓
[ Inspect captured page evidence & select an associated candidate:
    e.g. data-testid="checkout-btn" or role="button", name="Checkout"
    Missing evidence blocks the proposal; scores are not verification. ]
                  ↓
[ Generates Code Diff Preview:
    - self.submit_btn = page.locator("#old-btn-id")
    + self.submit_btn = page.locator("[data-testid='checkout-btn']") ]
                  ↓
[ User Reviews & Clicks "Apply Repair to Code" ]
                  ↓
[ Platform safely updates workspace Page Object file ]
                  ↓
[ User Clicks "Re-run Test Case" to verify fix passes ]
```

---

## 4. Strict Safety Principle: Proposal-Only

AI self-healing **NEVER** silently modifies code or alters test verdicts in the background:
- All repair proposals require explicit user inspection and approval (`POST /api/failures/{id}/apply-repair`). Recorder-linked evidence informs candidate discovery only; it never authorizes source edits.
- Re-run verification confirms fix correctness via standard pytest assertion.
