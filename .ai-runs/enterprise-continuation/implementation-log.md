# Implementation Log — 本轮实际改动

分支：`agent/wsl-continuation`（基于 `d8a2eef`，未修改、未合并、未推送 main）
日期：2026-10-16

## D1 — 验收夹具硬编码系统 Chrome，Linux/WSL 下必然失败（P1，跨平台）

**发现方式**：在 WSL 上第一次真实运行链路 A 验收。

```
playwright._impl._errors.Error: BrowserType.launch: Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome
Run "playwright install chrome"
```

失败点在被测工作区中生成的 `tests/test_verification_panel.py`，由平台 Runner 实际执行。

**根因**：前任 Agent 在 macOS 上开发时为绕开 bundled Chromium 的问题，把 `channel="chrome"`
写死进生成测试源码：

- `apps/api/tests/test_live_enterprise_journey.py`（生成的 f-string 内，约 m00063 记录的 71 行附近）
- `apps/api/tests/test_live_locator_repair_acceptance.py`（3 处：两个生成的 f-string 夹具 + 1 处真实 async launch）

**修复**：两个测试模块增加模块级

```python
BROWSER_CHANNEL = os.environ.get("AI_QA_ACCEPTANCE_BROWSER_CHANNEL") or None
```

生成源码中的字面量改为 `channel={BROWSER_CHANNEL!r}`，真实 launch 改为 `channel=BROWSER_CHANNEL`。
默认 `None` = 使用 Playwright bundled Chromium，在 Linux/WSL/CI 可直接运行；
只有确实无法运行 bundled Chromium 的宿主才需要 `AI_QA_ACCEPTANCE_BROWSER_CHANNEL=chrome`。

**未改动的相似代码**：`apps/api/tests/test_failure_snapshot.py:235` 的
`for channel in ("chrome", "msedge")` 是在**测试降级阶梯本身**，属于被测行为，保持不变。
产品代码 `apps/api/app/adapters/playwright/proxy.py:36` 的 `launch_chromium` 本来就是
bundled-first + msedge/chrome 回退 —— 产品无缺陷，只有测试夹具错了。

**验证**：`1 failed / 1 passed` → `2 passed`；`ruff check` / `ruff format --check` 通过。

---

## D2 — Web 生产构建 Node 堆溢出（P1，交付阻断）

**发现方式**：`pnpm --filter web build`（CI 中 `apps/web` 的 build 步骤使用同一命令）。

```
FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory
[ELIFECYCLE] Command failed with exit code 134.
```

V8 在约 2030 MB 处失败，说明默认 old-space 上限为 2 GB（本机 WSL 共 7.9 GB，不是宿主内存不足）。

**修复**：`apps/web/package.json`

```diff
- "build": "tsc -b && vite build",
+ "build": "tsc -b && node --max-old-space-size=4096 node_modules/vite/bin/vite.js build",
```

**为什么不是 `NODE_OPTIONS=...`**：AGENTS.md 要求跨平台（macOS/Linux/Windows），
`VAR=value cmd` 在 Windows `cmd.exe` 下不生效；`node --max-old-space-size` 三平台一致，
且不需要引入 `cross-env` 依赖。`node_modules/vite/bin/vite.js` 由 pnpm 直接依赖链接保证存在。

**验证**：`pnpm --filter web build` 成功，43.4 s。

**遗留技术债（未在本轮修）**：构建产物中 `MonacoEditorPane` chunk 4.03 MB（gzip 1.04 MB），
超过 500 kB 告警阈值。根因是 `apps/web/src/features/automation-studio/monaco.ts:1`
的 `import * as monaco from 'monaco-editor'` 拉入全部语言包。改为按需引入
`monaco-editor/esm/vs/editor/editor.api` + 仅需要的语言贡献，可同时降低包体与构建内存峰值，
但对 Studio 有回归风险，需要配套的浏览器验收，因此单独列为后续项。

---

## D3 — 健康探针预算小于 AI 请求超时，UI 误报「部分能力受限」（P1，状态一致性）

**发现方式**：真实浏览器验收时，`/library`、`/recorder`、`/settings` 等页面顶栏长期显示
「部分能力受限：常规 AI 运行健康与 AI 使用记录」，但同一时刻真实 AI 验收刚刚通过。

```
GET /api/ai/system-health  → overall "degraded"
    ai: status "warning", operational_state "PROBE_TIMEOUT",
        "Health probe did not finish within 15s; availability was not confirmed."
GET /api/ai/status         → REAL_CONNECTED, real_model_available: true, latency 21.4 s
```

两个端点自相矛盾：`platform_health_service.py` 给 `ai` 探针 15 s 预算，
而 `config/config.yaml` 的 `ai.timeout_seconds` 是 30 s，即**平台自己允许的 AI 请求超时比它的健康探针预算更长**。
另外 `_ai` 探针实际执行两次 provider 调用（`check_health()` + 一次合成 `stream_complete`），
所以真实耗时可以在 6 s ~ 40 s+ 之间波动。

**修复（后端）**：`apps/api/app/services/platform_health_service.py`

- `probe(name, callback, timeout=None)` 支持逐组件预算覆盖；
- 新增 `_ai_probe_timeout()`：`max(self._probe_timeouts["ai"], 2 * config.timeout)`
  —— 2 倍是因为探针发出两次 provider 调用，与 `_jev` 用固定 20 s 覆盖 20 s 请求超时的既有模式一致。

**修复（前端）**：探针超时只表示「未能及时确认」，不等于「能力受限」。
`apps/web/src/components/ReadinessNotice.tsx` 原先的过滤条件
`item.status === 'error' || (item.component === 'ai' && item.status !== 'ok')`
把 `PROBE_TIMEOUT` 也当成能力缺失。抽出纯函数
`limitedCapabilityComponents()`（`apps/web/src/components/readinessNoticeModel.ts`），
把 `operational_state === 'PROBE_TIMEOUT'` 排除，同时保留对真实不可用
（`SIMULATION` / `UNAVAILABLE` / `PROBE_FAILED` / `error`）的提示。

**验证**：

| 检查 | 修复前 | 修复后 |
| --- | --- | --- |
| `GET /api/ai/system-health?refresh=true` | `degraded`，`ai: warning / PROBE_TIMEOUT (15010 ms)` | `healthy`，`ai: ok / READY (3474 ms)` |
| 顶栏 `.notice-strip` 数量（/library、/settings、/quality） | 3/3 页显示 | **0/3 页显示** |
| `uv run pytest apps/api/tests/test_platform_health.py` | — | 6 passed |
| `pnpm --filter web test` | 153 passed | **157 passed**（新增 4 条） |
| typecheck / lint | 0 | 0 |

新增回归测试：

- `apps/api/tests/test_platform_health.py::test_ai_probe_budget_is_never_stricter_than_the_configured_ai_timeout`
  —— 钉住不变量：`timeout=30 → 60`，`timeout=5 → 15`（保留下限）。
- `apps/web/tests/readiness-notice-model.test.mjs` —— 4 条：全健康无限降级、
  `PROBE_TIMEOUT` 不触发、真实不可用仍触发、非 AI 的 warning 不触发。

---

## D4 — Agent 交接机制（流程，非代码缺陷）

新增：

- `docs/agent-handoff.md`（版本控制内），含当前 SHA、分支、阶段、已完成/已验证/未完成、
  已知 Bug、阻断、最后测试、下一步命令。
- `AGENTS.md` 增补「长期 Agent 开发交接规则」章节，要求任何跨会话任务都必须维护该文件，
  且禁止把聊天记录或未跟踪临时日志当作唯一进度来源。
- `.ai-runs/enterprise-continuation/` 下的审计证据（Markdown），
  其中大型运行日志按仓库既有约定（`.gitignore` 第 129 行忽略 `*.log`）保留在本地不提交。

**动因**：前任 Agent 的最终回归日志
`.ai-runs/enterprise-platform-upgrade/logs/backend-final.log` 被 commit message 引用，
但磁盘与 Git 历史中都不存在，导致最后一次回归无法复核（见 `recovery-audit.md` R1）。

## 未修复（有意保留）

| 项 | 原因 |
| --- | --- |
| Studio 的 Monaco 全量导入（4 MB chunk） | 需要配套浏览器回归，风险大于收益，列为后续项 |
| `platform_health_service._probe_timeouts` 的 `jev` / `browser` 仍为常量 | 本轮未观测到误报，避免无谓改动 |
| 33 个 service 直接使用 `session.execute` | 架构债务，非缺陷 |

---

## D5 — Discovery → Coverage 下游刷新与过期执行选择

**现象**：真实 Quality Discovery 终态已持久化 Quality Map，但之后的 TestRun 不会更新 Discovery 结果中的覆盖率快照；UI 停止轮询后会一直展示旧覆盖率。

**修复**：新增终态限定的 `POST /api/discovery/runs/{run_id}/coverage/refresh`，校验 `RUN_EXECUTE`，非管理员只能刷新自己发起的 run；active run 返回 409、未知/非所有者 run 返回 404。UI 的 Discover Map 增加刷新按钮、busy/error/success 状态，并在切换 run 时清除旧反馈。OpenAPI 声明 403/404/409。

**准确性与并发**：`_latest_execution()` 现在从匹配到真实 browser session 的 executions 中选择 `started_at` 最新的一条（回退 `finished_at`，再回退 run 创建时间）；新增并发 refresh 及多 execution 回归。WeakValueDictionary lock 在 async waiter 的局部变量中保持强引用，双 refresh 测试观测到 projection 最大并发为 1；多进程/多 worker 仍未验证。

**真实验收**：`test_real_local_discovery_preserves_target_and_project_scope` 使用真实 `openai-compatible` AI、真实 Jev、真实本地浏览器，生成 requirement/case、写入人工编写 Playwright 测试、激活 binding、实际执行并 `POST refresh`：Discovery `qd_d8decd8513c540af` → case `tc_f52bf659a447` → TestRun `run_f588b51d68fb` PASSED → coverage `VERIFIED`，AI generation `fallback_used=false`，Jev `fallbacks=0`。`1 passed in 63.29s`，仅在本轮 acceptance 命令中放宽 AI timeout 至 60s/retries 1；默认 20s 曾真实超时，须保留为 provider 稳定性风险。

**验证**：`test_quality_discovery.py` 64 passed；Web tests 160 passed、typecheck、lint、production build 通过。新按钮尚未由真实 Web UI 浏览器点击验收；历史失败修复 UI 链路已通过真实浏览器。全仓最终回归仍待执行。

**遗留边界**：项目模型无 project owner/team ACL，中央 RBAC 当前是全局角色；本 endpoint 的 requester/admin 限制不等于完整 project-level isolation，其他既有 API 仍需系统级授权设计。
