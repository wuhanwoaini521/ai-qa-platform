# 外部框架机制学习

状态：**学习完成，未安装、未运行**。
所有「官方陈述」来自官方文档或对应 tag 的源码；所有「本项目实测」为空——本轮没有执行任何候选框架。
核实日期：2026-10-29。

---

## 1. 基线事实

| 框架 | 版本 | 许可证 | 关键依赖约束 | 与本项目冲突 |
|---|---|---|---|---|
| LangGraph | 1.2.18（2026-10-26） | MIT | Python `>=3.10`；`langgraph-checkpoint>=4.3,<5` | 无直接版本冲突；但它是编排库，会形成第二套状态源 |
| Browser Use | 0.13.14（2026-10-26） | MIT | Python `>=3.11,<4.0`；顶层 manifest 未固定 Playwright | Playwright 传递依赖与 1.62.0 的兼容性 **UNKNOWN** |
| Skyvern | v1.0.56（2026-10-14） | **AGPL-3.0** | `playwright==1.56.0`；`fastapi>=0.136.1,<0.137`；Python `>=3.11,<3.15` | 与本项目 Playwright **1.62.0**、FastAPI **0.141.1** 直接冲突 |

> 修正：研究分支记录 Skyvern 为 `playwright>1.46.0`。当前 tag 的 manifest 是 `playwright==1.56.0`，更严格。以本次核对为准。

---

## 2. LangGraph

### 2.1 机制事实（官方文档）

| 机制 | 官方陈述 | 与本项目对照 |
|---|---|---|
| 持久化粒度 | 每个 **super-step** 边界创建 checkpoint；一个 super-step 内所有就绪节点一起执行 | 本项目用 **TaskStep** 粒度，比超步更细，语义同构 |
| 恢复起点 | 从最后 checkpoint 恢复；已完成的 task 不重跑；**已开始但未完成的 task 可能再次运行** | 本项目恢复是围栏式 BLOCKED，不重放 |
| 中断 | 节点内调用 `interrupt()`；恢复时 **整个节点从头重跑**，不从断点行继续 | 本项目 `ApprovalRequired` 后由步骤边界继续，语义接近但更严格 |
| 副作用 | 官方明确：`interrupt` 之前的副作用应幂等；**建议把副作用放到 interrupt 之后**，或拆到独立节点 | 本项目审批前生成 diff、审批后应用，方向一致 |
| 幂等 | 官方只用「设计成幂等 / 用幂等键或校验已有结果」，**不承诺 exactly-once** | 本项目已有 `workflow_idempotency_key` 唯一约束 |
| 审批过期 | 官方**未定义** interrupt/审批的 TTL 或旧审批拒绝机制 | 本项目有按 `current_step_id` + `WAITING` 的条件抢占，比框架更明确 |
| 重试 | 默认 `max_attempts=3`、`backoff_factor=2.0`、`jitter=True`；默认不重试 `ValueError/TypeError/RuntimeError/OSError`；HTTP 只重试 5xx；超时仅 async 节点，超时会清除该次写入 | 本项目按工具名白名单重试，无 jitter，无错误分类 |

来源：`docs.langchain.com/oss/python/langgraph/{checkpointers,interrupts,use-time-travel,fault-tolerance}`，读取于 2026-10-29。

### 2.2 可借鉴（零依赖）

1. **审批后置副作用**：审批前只产出 diff/预览，审批后才执行写入。本项目已基本如此，需要在工具分类层面固化。
2. **attempt 级幂等键**：外部写入使用 `task.id + step.id + retry_count` 作为幂等键，写入侧做唯一约束。现有 `workflow_idempotency_key` 只覆盖工作流创建，未覆盖步骤级外部写入。
3. **错误分类重试 + jitter**：把「瞬时错误 / 不可重试 / 需人工」分开，退避加抖动，避免重试风暴。
4. **超时清除本次写入**：超时不是「写入成功但标记失败」，而是本次尝试作废。

### 2.3 不借鉴

- 用 checkpointer 替换 `TaskORM` / 事件流：会形成第二套状态源，违反 ROADMAP §0 第 6 条。
- 直接嵌入其图执行器：等于第二套调度器。

### 2.4 结论

LangGraph 的价值是**三条契约**（超步快照、未完成至少执行一次、副作用幂等），不是「框架」本身。
本项目已用 TaskStep + lease + 条件 UPDATE 实现同构语义，粒度更细；需要补的是**错误分类**与**步骤级幂等键**。

---

## 3. Browser Use

### 3.1 机制事实（官方文档 + tag 源码）

| 机制 | 实现方式 | 与本项目对照 |
|---|---|---|
| 分层 | Agent 决策 → Registry 动作 → 浏览器会话；会话由 `BrowserSession` 持有 | 本项目 `BrowserRuntime` 持有会话，Discovery 只发语义动作，方向一致 |
| 会话管理 | `storage_state` / `user_data_dir`；`_storage_state_watchdog`、`_crash_watchdog`、`is_reconnecting`、`RECONNECT_WAIT_TIMEOUT` | 本项目有 TTL + 生命周期锁 + `is_connected()` 检查，**缺断连分类与有限等待** |
| 页面理解 | CDP `Accessibility.getFullAXTree` 合并所有 frame；可交互元素分配 `selector_index` → `selector_map` | 本项目用 `aria_snapshot` + `collect_controls()`（≤100）+ 截图 + tabs；**缺「快照代次」概念** |
| 动作执行 | Pydantic ActionModel + Registry；按索引取元素，索引失效返回「page may have changed」 | 本项目按 locator 候选执行，天然避开陈旧索引，但 UI 高亮/下标可能漂移 |
| 失败恢复 | `max_failures`、`consecutive_failures`、`step_timeout`、`loop_detection_window`、停滞时注入 replan 提示 | 本项目有 `max_failures`、预算、状态指纹去重；**缺显式停滞计数与动作重复终止规则** |
| 成功判定 | **agent 自评** `is_successful`，官方亦提示需独立验证 | 本项目坚持 Pytest 退出码，**不采用自评** |

### 3.2 可借鉴（零依赖）

1. **快照代次（observation_id）**：给每次 `snapshot()` 的 controls 绑定代次；点击旧代次的索引时返回明确失效错误，而不是误点。
2. **断连分类**：区分「页面已关闭」「浏览器断开」「网络错误」，只在可恢复类别上做有限等待。
3. **停滞检测**：同一动作重复 N 次且状态指纹不变 → 确定性终止，而不是继续消耗预算。
4. **动作失效显式报错**：`STALE_TARGET` / `AMBIGUOUS_TARGET` 作为独立终态，便于诊断。

### 3.3 不借鉴

- LLM-first 的自评成功判定。
- 让框架接管浏览器会话（会形成第二个 Playwright 所有者）。
- 其 54 秒重连常数——需要本项目自己的测量。

### 3.4 结论

Browser Use 的分层与本项目一致；真正值得学的是**索引失效处理**与**停滞检测**，这两点能直接降低 Discovery 的误操作与预算浪费。

---

## 4. Skyvern

### 4.1 机制事实（官方文档 + tag 源码）

| 机制 | 实现方式 | 与本项目对照 |
|---|---|---|
| AI 与 Playwright 分工 | LLM 规划与推理，Playwright 执行；SDK 支持 selector-only / NL-only / selector-first-AI-fallback | 本项目 `DecisionService` 选候选，`TaskBrowserExecutor` 执行，方向一致 |
| 状态模型 | `TaskStatus`：created/queued/running/timed_out/failed/terminated/completed/canceled，有合法迁移表；`WorkflowRunBlock` 有 `status/attempt_number/failure_reason/error_codes`；**无 checkpoint 或幂等键字段** | 本项目 TaskStatus 更细，且 lease+fencing 更强 |
| 页面交互 | JS 给可交互元素打 `SKYVERN_ID_ATTR`，建 id→CSS 映射；hash 忽略 id/rect/frame_index；iframe 递归合并；detached 元素走 `StaleActionAbort`；select 先确定性匹配，失败才 LLM fallback | 本项目有多候选 locator 与 effect 校验；**缺结构指纹去重与 stale 分类** |
| 数据提取 | Data Schema 是 JSON Schema，保存时校验；响应校验失败重试一次 | 本项目在 workflow graph 校验与 discovery payload 上有类似约束，但**没有通用结构化输出校验** |
| 证据 | artifact 类型含 recording、session_replay、screenshot、html、trace、har、visible_elements_tree、llm_prompt/request/response；artifact 带 checksum | 本项目证据更细（DOM/network/user_action），**缺 session replay 与统一 checksum** |
| 许可证 | AGPL-3.0；README 只说核心逻辑是 AGPL，未解释网络服务义务 | 本项目无同类约束；**需专业法务评估** |

### 4.2 可借鉴（零依赖，且不复制源码）

1. **结构指纹去重**：对元素树做忽略 id/rect 的 hash，合并重复元素，减少候选数量与误点。
2. **stale target 显式分类**：元素 detached 后中止并重新观察，而不是继续重试。
3. **结构化输出校验**：在 provider 边界对 JSON Schema 做一次校验，失败重试一次；仍失败则明确失败。
4. **artifact 类型分层与 checksum**：与本项目 F7 的改进方向一致。

### 4.3 不借鉴

- 自托管 Skyvern 服务：会引入第二套任务/浏览器/证据所有权。
- 其依赖栈：`playwright==1.56.0` 与项目固定的 1.62.0 冲突，`fastapi<0.137` 与 0.141.1 冲突。
- 任何源码复制：AGPL-3.0 义务未评估。

### 4.4 结论

Skyvern 的工程细节（稳定句柄、结构 hash、stale 分类、artifact 分层）值得学；**代码与依赖都不应引入**。

---

## 5. 横向对比：三个框架共同在解决什么

| 问题 | LangGraph | Browser Use | Skyvern | 本项目现状 |
|---|---|---|---|---|
| 崩溃后从哪里继续 | 超步 checkpoint | 会话重连 | 块级重跑 | step 级围栏恢复（不重放） |
| 副作用重复 | 幂等键（不保证 exactly-once） | 动作索引失效校验 | stale abort | 部分：工作流幂等键，步骤级缺失 |
| 人在回路 | interrupt/resume | 无专门机制 | 无专门机制 | 已有审批步骤与条件抢占，最明确 |
| 浏览器状态 | 不涉及 | 会话 watchdog | 元素句柄 | 进程内会话 + TTL，无跨进程 |
| 证据 | checkpoint 状态 | 步骤截图/日志 | 全量 artifact + checksum | 分域证据，无统一 hash |

**结论**：本项目在「判定权威」和「审批边界」上已经强于三个框架；差距集中在**副作用幂等**、**证据完整性**、**浏览器交互的失效处理**。

---

## 6. 借鉴清单 → 对应里程碑

| 借鉴点 | 来源 | 对应缺陷 | 里程碑 |
|---|---|---|---|
| 审批后置副作用 | LangGraph | F5 | M3 |
| 步骤级幂等键（task+step+attempt） | LangGraph | F5 / F7 | M3 |
| 错误分类 + jitter 退避 | LangGraph | F5 | M3 |
| 超时作废本次写入 | LangGraph | F3 | M2 |
| 快照代次与失效报错 | Browser Use / Skyvern | Discovery 误点 | 后续（未排期） |
| 停滞检测确定性终止 | Browser Use | Discovery 预算浪费 | 后续（未排期） |
| 结构化输出 Schema 校验 | Skyvern | provider 输出形状 | 后续（未排期） |
| artifact checksum | Skyvern | F7 | M6 |

「后续（未排期）」表示：已有明确借鉴点，但当前没有用户可见故障证据，不进入前 7 个里程碑。

---

## 7. 未验证项

- 三个框架均**未安装、未运行**；所有运行行为 UNKNOWN。
- Browser Use 的 Playwright 传递依赖未解析。
- Skyvern 的恢复行为、artifact 体积、Temporal 依赖未验证。
- Skyvern 的 AGPL 义务对具体部署形态的影响：**需专业法务评估**。
- LangGraph 是否有内建审批 TTL：官方文档未述，UNKNOWN。
