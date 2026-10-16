# WSL Environment Audit — enterprise-continuation

Run date: 2026-10-16
Host: WSL2 on Windows (`AA0125060005-LP`), Ubuntu 22.04.5 LTS, kernel `6.6.87.2-microsoft-standard-WSL2`, x86_64.

## 1. Repository

| Check | Result |
|---|---|
| Working directory | `/home/hans/self-github/ai-qa-platform` |
| Git HEAD | `d8a2eef2730b979dc172a9b78393105876b46dc8` |
| Branch | `main` (== `origin/main`, ahead 0 / behind 0) |
| Remote | `git@github.com:wuhanwoaini521/ai-qa-platform.git` |
| Dirty state at start | only `AGENTS.md` modified (long-term handoff rule added by the incoming agent) |
| Untracked files | none |
| Windows duplicate copy | **none found** — searched `/mnt/c/Users/**/ai-qa-platform`, `/mnt/d`, and `/home/hans`; only this Linux copy exists |
| Baseline commit | `d8a2eef` matches the handoff expectation (previous baseline `02c5f3c`) |
| Line endings | no CRLF in any tracked file; `core.autocrlf` unset; no `.gitattributes` |
| `.ai-runs` | 33 run directories, 593 tracked files; `*.log` is git-ignored (line 129 of `.gitignore`) |
| Case sensitivity | ext4 (Linux, case-sensitive) |

**Finding:** the handoff referenced `.ai-runs/enterprise-platform-upgrade/logs/backend-final.log` as the
authoritative record of the previous agent's final regression. **That directory does not exist** — neither on
disk nor in Git history. The previous run's raw log is unrecoverable. See `recovery-audit.md`.

## 2. Toolchain

| Tool | Version | Source | Notes |
|---|---|---|---|
| Python | 3.13.16 | mise (`mise.toml` pins `3.13`) | matches CI (`uv python install 3.13`) |
| venv | `.venv`, CPython 3.13.16 | `uv venv --python 3.13` | see finding below |
| uv | 0.13.1 | `~/.local/bin/uv` | `mise ls` reports the mise-managed `uv` as "(missing)", PATH uv is used |
| Node | 24.22.0 | mise | `mise.toml` pins `24`; matches CI |
| pnpm | 12.5.1 (repo `packageManager`), 12.13.0 (mise) | repo root `package.json` | CI uses the repo-pinned version |
| Playwright (Python) | 1.62.0 | `apps/api/pyproject.toml` | pinned exactly; **no 1.63+ installed** |
| Chromium (Playwright) | `chromium-1234` / `chromium_headless_shell-1234` | `~/.cache/ms-playwright` | installed during this audit; launches and renders headless |
| git | 2.34.1 | `/usr/bin/git` | |
| gh | present | `/usr/bin/gh` | |
| docker | **MISSING** | — | Docker daemon unavailable |
| psql / pg_isready | **MISSING** | — | PostgreSQL lane cannot run |
| system chrome / chromium | **MISSING** | — | irrelevant: bundled Playwright Chromium is used |

### Environment finding E1 — venv initially built on Python 3.11 (fixed)

A bare `uv sync --all-packages` outside `mise exec` created `.venv` with CPython **3.11.14**, while
`mise.toml` and CI both pin **3.13**. The venv was recreated with `uv venv --python 3.13` and re-synced;
`.venv/pyvenv.cfg` now reports `version_info = 3.13.16`. Root cause: uv resolves its own interpreter when
`mise exec` is not on the invocation path; `scripts/task.py` already routes through `mise exec --`, so the
supported entry point (`python scripts/task.py setup`) does not hit this. No repository change needed.

### Environment finding E2 — Playwright browsers were not installed (fixed)

The first backend run failed
`test_agent_tasks.py::test_browser_agent_completes_second_ecommerce_journey_on_demo_shop` with
`BrowserType.launch: Executable doesn't exist at /home/hans/.cache/ms-playwright/chromium...`.
`uv run playwright install chromium` installed build 1234 (the build pinned by Playwright 1.62.0) and the
suite passes. This is expected on a fresh Linux checkout — Windows' browser cache does not transfer.

## 3. Configuration

`.env` exists (not committed) and selects **real** providers:

- `QA_AI_ENABLED=true`, `QA_AI_PROVIDER=openai-compatible`, `QA_AI_BASE_URL=https://opencode.ai/inference/go/v1`
- `JEV_ENABLED=true`, `JEV_BASE_URL=https://api.typesafe.ai/v1/systemone`, `JEV_MODEL=jev-1.13.0`
- `QA_AI_API_KEY`, `JEV_API_KEY`, `APP_SECRET_KEY` are all set (values not printed)
- Persistence: SQLite at `runtime/ai_qa_platform.db` (PostgreSQL configured but unreachable)

DNS/network from WSL resolves `opencode.ai`, `api.typesafe.ai`, `registry.npmjs.org`. During this session
the AI tunnel intermittently returned `502 cannot resolve tunnel destination opencode.ai (ETIMEDOUT)` —
real AI/Jev calls are subject to that upstream flakiness and must be retried.

## 4. Services and ports

At audit start, **no project services were running**. Ports 8000 (API) / 5173 (Vite) were free; the only
listeners were WSL-internal DNS resolvers. `scripts/task.py dev` is the standard way to start both, and it
waits for `GET /api/health/live` before starting Vite.

## 5. Cross-platform code review

A repo-wide scan for Windows assumptions found them all **correctly guarded**:

- `packages/qa-core/qa_core/execution/pytest_runner.py:59` — `taskkill` only under `os.name == "nt"`, else `os.killpg`.
- `packages/qa-core/qa_core/execution/pytest_runner.py:100-101` — `creationflags` on Windows, `start_new_session` elsewhere.
- `scripts/task.py:32,106` — `IS_WINDOWS` guards `taskkill` and reload/signal handling.
- `apps/api/app/services/python_language_service.py:86` — `node.exe` vs `bin/node`.
- `apps/api/app/adapters/playwright/browser_runtime.py:20` — user-agent platform token per OS.
- `apps/api/app/services/workspace_service.py:101` — Windows event-loop caveat only.

Remaining `C:\` literals are **test fixtures** that assert traversal rejection (`test_runs_and_failures.py:104`,
`test_recorder_save_flow.py:59`, `test_project_pilot.py:550`, etc.), not runtime path construction.
Searches performed: `C:\\`, `C:/`, `Program Files`, `taskkill`, `APPDATA`, `LOCALAPPDATA`, `os.name`,
`sys.platform`, `platform.system`, `os.sep`. **No unguarded Windows-only path or command was found.**

## 6. Environment limitations (carried into acceptance)

| Gate | Status |
|---|---|
| PostgreSQL lane | **BLOCKED** — no `docker`, `psql`, `pg_isready` |
| Remote/separate Worker service | **NOT RUN** — no worker registered; API-local execution only |
| Windows lane | **NOT RUN** — this host is Linux |
| System browser channel | not needed; bundled Playwright Chromium works |
