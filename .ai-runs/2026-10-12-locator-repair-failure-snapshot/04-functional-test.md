# Functional Tests

## Targeted behavior

- `uv run --no-sync --package qa-core pytest -q packages/qa-core/tests/test_live_browser_telemetry.py` — **7 passed**。覆盖真实 Playwright failure snapshot、加密状态、脱敏数据、基线缺失/捕获。
- `uv run --no-sync --package worker pytest -q apps/worker/tests/test_worker.py` — **8 passed**。覆盖既有 worker runner 路径的加密快照传输。
- API 快照/工作流/迁移相关测试 — **58 passed**（在全量回归前运行）。覆盖 TTL、证据不足、工作流及迁移。
- 全量 API：`uv run --no-sync --package api pytest -q apps/api/tests` — **557 passed, 8 skipped**。其中包含本地登录保护页面 fixture 的真实 Playwright 状态恢复与 locator 验证验收；Jev 选择由测试 stub 提供。
- `pnpm --filter @ai-qa/web typecheck` — 通过。

## Repository checks

- `python scripts/task.py lint` — 通过：Ruff、Ruff format、i18n parity（25 namespaces / 2 languages / 2906 keys）、ESLint。
- `uv lock --check` — 通过。
- `python -m compileall -q ...`（API、迁移、worker、qa-core、project-model、platform-config）— 通过。
- `git diff --check` — 通过。

API 测试输出含既有 pytest collection / SQLAlchemy cleanup warnings；未出现失败。外部真实 Jev 服务验收未在本快照任务中执行。
