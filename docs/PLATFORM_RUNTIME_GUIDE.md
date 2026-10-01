# Platform Runtime Guide

这份文档概述一次测试从创建到结果、Live Browser、Failure、Debug 和 AI/Jev 决策的运行链路。更细的 Runner、Recorder、Provider 配置见 [RUNNER_ARCHITECTURE.md](RUNNER_ARCHITECTURE.md)、[BROWSER_RECORDER.md](BROWSER_RECORDER.md)、[AI_PROVIDER.md](AI_PROVIDER.md) 和 [DECISION_LAYER.md](DECISION_LAYER.md)。

## How Test Run Works

`TestRunService` 创建并持久化 `run_id`，再调用现有 pytest runner（本地）或 Jenkins backend。pytest 结果按 node ID 写入 `TestCaseExecution`，其数据库 ID 是 `case_execution_id`。xdist worker 用 `worker_id` 标识；Live Browser telemetry 以 `run_id + worker_id + nodeid` 关联执行，并在匹配到执行记录后补齐 `case_execution_id`。浏览器会话有独立 `browser_session_id`，不通过 case title 推断归属。

```text
TestRun (run_id)
  └─ TestCaseExecution (case_execution_id, nodeid)
       ├─ Worker (worker_id)
       ├─ BrowserSession (browser_session_id)
       ├─ Failure / logs / artifacts
       └─ DebugSession (debug_session_id, explicitly created from a case)
```

本地 runner 会将 telemetry plugin 写入本次 run 的 artifacts 目录。plugin 观察测试 fixture 正在驱动的 Playwright page，并通过 Chromium CDP screencast 读取真实帧；不会再开一个浏览器来伪装测试状态。Frame 通过 run SSE 临时传输，session、worker、node ID、URL 和状态作为运行元数据保存。Frame 不持久化。Jenkins runner 通过远端构建和日志提供结果；远端 Live Browser 帧取决于远端 worker 是否运行相同的 telemetry plugin。

## Live Browser Architecture

`LiveBrowserPlugin` 为每个 xdist worker 单独写入事件文件，API tail 事件并发布到该 run 的 SSE channel。事件包含 session start、navigation、frame 和 finish；UI 以 worker/session tab 选择单一主视图，其余 worker 保留紧凑状态。SSE 断开时，浏览器端会申请新的短期票据并重连，Run detail 通过 API 恢复持久化状态；历史 frame 不回放，界面会显示等待/重连状态。

当前真实帧链路基于 Chromium CDP。其他浏览器引擎或不支持 CDP screencast 的页面仍能报告 session 和 navigation 元数据，UI 不生成替代帧。

## Cancellation and Cleanup

Run 状态只允许从 `QUEUED` / `RUNNING` 原子迁移到终态。重复取消终态 run 是幂等操作；迟到的 runner 结果、日志或 worker 更新不能覆盖 `CANCELLED`。远程 Worker 轮询 job 状态，检测到取消后取消 pytest task；runner 负责结束其子进程树。对已取消的分布式 job，API 会同步标记活跃 job 为 `CANCELLED`。

Startup stale recovery 只处理本机 `LOCAL` run。`WORKER` 和 Jenkins 由各自的执行控制面管理；worker heartbeat 尚未被用来推断单个 job 的失效，因此 stale worker job 的 lease reconciliation 仍是后续工作。每个已提交的 case result 与取消共享 Run 行的数据库写锁；若取消先提交，迟到结果不会再增加执行记录；若 case 结果先提交，取消时的通过/失败/跳过计数会包含它。

## Stream Credentials and URL Redaction

Run/task SSE 使用服务端签发的 5 分钟 stream ticket 放在 `Authorization` header 中；Recorder/Debugger WebSocket 在连接后的首帧发送 ticket。Ticket 只允许读取单个 run、task、recorder 或 debug session 的 stream，不能作为普通 API bearer 使用。凭证不放在请求 URL；重连时前端申请新 ticket。

进入 BrowserSession、SSE、Locator Decision、AI trace、文本日志和 task evidence 的 HTTP(S) URL 会移除 userinfo、query 和 fragment；`data:`、`blob:`、`file:` 等可能包含正文或本机路径的非 HTTP URL 只保留 scheme。执行导航仍使用原始 URL，避免破坏测试输入。

## Debug Runtime

工作室顶部“调试”运行当前测试文件中的全部用例，使用该文件及 workspace 中启用的断点；有未保存编辑时先保存，保存失败不会启动。测试树或失败详情中的调试入口仍运行指定用例。调试面板显示实际启动目标，避免把第一条已收集用例误当成当前文件。pytest 停在可执行行，函数声明、空行等断点位置可能由 debugpy 调整。

Debugger 由独立的 `DebugSessionService` 为经授权的 debug session 启动一个 debugpy DAP adapter；它复用项目 workspace 和选定的 pytest node ID，不复用或重启 Run 的浏览器。`debug_session_id` 隔离会话，session 绑定 owner。源文件路径必须位于 workspace 内，客户端请求仅允许明确支持的 DAP commands。停止或关闭 debug session 时应结束 adapter 及相关 task。Debugpy 不可启动时返回明确错误，不显示虚假的 Running 状态。

## AI → Jev Flow and Provider States

常规 AI provider 负责 QA 助手、需求/用例处理和失败分析；Jev 是独立的结构化决策 provider，可用于 locator candidate 决策等场景。两者配置、密钥和健康状态相互独立。Locator candidate 在落地前由现有 Playwright verification 执行验证；决策或 AI 输出不直接等价于 locator 已可用，修复仍由用户确认后应用。

AI 运行状态区分 `REAL_CONNECTED`、`FALLBACK`、`SIMULATION` 和 `UNAVAILABLE`；普通 provider health 另有 `AVAILABLE`、`DISABLED`、`AUTH_ERROR`、`RATE_LIMITED`、`TIMEOUT` 和 `UNAVAILABLE`。选中 Fake provider 明确显示为 simulation。Jev 请求超时、不可用、低于置信度阈值或配置关闭时使用 Local Strategy/unknown abstention，并将 fallback 原因和调用元数据记入 trace；不能将 fallback 报告为真实 Jev decision。

## Failure Flow

失败详情的分析流程按 UI、API、Python 证据选择检查阶段，实时显示每步事件、来源与耗时。`failure_analyses` 保存每次分析及取消、失败、中断状态，重新打开页面可以回顾。模型输出不能覆盖日志已经确定的错误分类，普通断言失败不会进入 Locator 修复。完整流程和验证规则见 [FAILURE_INTELLIGENCE.md](FAILURE_INTELLIGENCE.md)。

pytest report 生成统一的 case execution 和 failure 记录；failure 通过 `case_execution_id` 关联 traceback、截图和最近的 browser session。traceback 定位优先选 workspace 中的用户代码帧，避免跳到 pytest/debugpy internals。UI 可从失败打开对应文件/行、创建 failure breakpoint 或启动该 case 的 DebugSession。AI 分析是独立附加步骤；AI 不可用不能改变已经确定的测试结果。
