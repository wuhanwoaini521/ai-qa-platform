# Developer Guide

## Prerequisites

- macOS, Linux or Windows
- `mise` installed for toolchain version management
- Git and GitHub CLI `gh`

Windows: `winget install jdx.mise`, then `mise install`. Git Bash is **not** required — every task
runs through `scripts/task.py`, which is plain Python.


## Toolchain Overview

The repository configuration is managed by `mise.toml`:
- **Python**: `3.13`
- **Node.js**: `24`
- **uv**: Latest (Python workspace manager)
- **pnpm**: `12.x` (Frontend package manager)

---

## Quick Setup

```bash
# 1. Clone repository
git clone git@github.com:wuhanwoaini521/ai-qa-platform.git
cd ai-qa-platform

# 2. Trust and install toolchain (Python 3.13, Node 24, uv) and dependencies
mise trust
pnpm setup

# 3. Start full-stack development environment
pnpm dev
```

`pnpm setup` is shorthand for `python scripts/task.py setup`, which runs `mise install`,
`uv sync --all-packages` and `pnpm install` in that order.

- **Backend API**: `http://127.0.0.1:8000` by default (Swagger UI at `/docs`)
- **Web Application**: `http://127.0.0.1:5173` by default

If a default port is already in use, the runner selects the next available localhost port and
prints the actual URLs. The Vite API proxy follows the selected backend port. Set
`AI_QA_API_PORT` or `AI_QA_WEB_PORT` to choose a different preferred port.

Press `Ctrl+C` to stop both servers. On Windows the runner kills the whole process tree, so the
`uvicorn --reload` grandchild is torn down with it and the selected API port is released.

### Entry Points

All three run the same implementation in `scripts/task.py`:

| Task | Command | Shell equivalent |
| --- | --- | --- |
| Install | `pnpm setup` | `make install` |
| Dev servers | `pnpm dev` | `make dev`, `./scripts/dev` |
| Tests | `pnpm test` | `make test`, `./scripts/test` |
| Lint | `pnpm lint` | `make lint`, `./scripts/lint` |
| Build | `pnpm build` | `make build` |
| Clean | `pnpm clean` | `make clean` |

`make` is optional. The `scripts/dev`, `scripts/test` and `scripts/lint` files remain bash shims for
existing macOS and Linux muscle memory; they simply delegate to the Python runner.


## Testing & Quality Assurance

```bash
# Backend unit, integration and security tests + frontend typecheck, lint & build
pnpm test

# Linters and format checkers (ruff & eslint)
pnpm lint

# Build production assets
pnpm build
```

The PostgreSQL lane is skipped unless `AI_QA_TEST_DATABASE_URL` is set:

```bash
AI_QA_TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/postgres' pnpm test
```


---

## Security & Path Integrity

- Workspace operations are restricted strictly to `runtime/workspaces/<id>`.
- Any path traversal (`../`, absolute paths, symlink escapes) will trigger a `SecurityException` and return HTTP 400.
- Runtime databases and test workspaces are excluded from Git commits via `.gitignore`.

---

## Internationalisation (zh-CN / en)

The web UI ships in Chinese and English, with a switcher in the top bar and a settings page at
`/settings` (language, sign-in landing page, default project).

Conventions:

- Translations live in `apps/web/src/i18n/locales/<language>/<namespace>.json`. Adding a namespace
  means adding the two files — `apps/web/src/i18n/index.ts` discovers them with a glob and never has
  to be edited.
- A feature owns its own namespace (`dashboard`, `studioShell`, `runs`, …) so two contributors never
  edit the same resource file. Shared vocabulary lives in `common` (`common:save`, `common:cancel`, …).
- **Both languages must carry the same keys.** `pnpm lint` runs `scripts/i18n_check.py`, which
  compares every namespace key-by-key and fails on a missing translation.
- Do not translate data: node ids, file paths, framework names, status values the API returns, log
  and JSON output. Translate the labels around them.
- Chinese copy should read like a QA engineer wrote it (`缺陷`/`用例`/`回归`), not like a machine
  translation of the English string.
