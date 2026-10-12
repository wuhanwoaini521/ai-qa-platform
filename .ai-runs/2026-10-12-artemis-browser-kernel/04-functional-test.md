# Functional and Integration Verification

## Current live AI + Jev acceptance

Command:

```bash
AI_QA_LIVE_BROWSER_E2E=1 AI_QA_LIVE_EVIDENCE_DIR=.ai-runs/2026-10-12-artemis-browser-kernel/evidence uv run pytest apps/api/tests/test_browser_agent_live_e2e.py -q -s
```

Result: **1 passed in 13.01s** against the final backend implementation.

The test used real configured providers (`openai-compatible` / `deepseek-flash` and Jev `jev-1.13.0`) with a local Playwright catalog. The goal was verified at `/products/blue-wool-jacket`; three browser actions succeeded. It persisted three successful AI invocations and three successful Jev invocations. For each action, the AI invocation, Jev invocation, decision event, action event, and action record shared the same correlation ID. The current run receipt is `evidence/live-browser-acceptance.json`; screenshots are `evidence/live-browser-action-01.png` through `03.png`.

## Automated regression

- `uv run pytest -q` — **683 passed, 8 skipped, 44 warnings in 328.67s**. Skips are opt-in/environment-dependent tests; the live-provider test was run separately as above. Warnings included pytest collection notices, one SQLAlchemy connection cleanup warning, and a syntax warning from a generated fixture.
- `pnpm --filter @ai-qa/web test` — **138 passed**.
- `pnpm --filter @ai-qa/web typecheck` — passed.
- `pnpm --filter @ai-qa/web build` — passed. Vite reported the existing large Monaco/editor chunk warning (>500 kB); no build failure.
- `python scripts/task.py lint` — passed: Ruff check, Python format check (405 files), translation parity (25 namespaces / 2 languages / 2,906 keys), and ESLint.
- `git diff --check` — passed.
- Focused history/redaction tests — `uv run pytest apps/api/tests/test_browser_agent.py -q`: **24 passed**.

## Browser UI interaction

Used `agent-browser` attached over CDP to installed system Chrome. Opened the project Recorder workspace, selected both strategies, and captured:

- `evidence/recorder-agent-strategy.png`
- `evidence/recorder-fast-strategy.png`
- `evidence/workspace-overview.png`

The live browser task was exercised through the task/browser execution service with real AI + Jev; a live task was not submitted through the UI button itself.
