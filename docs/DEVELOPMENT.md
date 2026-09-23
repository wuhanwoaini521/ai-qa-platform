# Developer Guide

## Prerequisites

- macOS or Linux development environment
- `mise` installed for toolchain version management
- Git and GitHub CLI `gh`

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

# 2. Trust and install toolchain
mise trust
mise install

# 3. Install dependencies
mise exec -- uv sync --all-packages
mise exec -- pnpm install

# 4. Start full-stack development environment
./scripts/dev
```

- **Backend API**: `http://127.0.0.1:8000` (Swagger UI at `/docs`)
- **Web Application**: `http://127.0.0.1:5173`

---

## Testing & Quality Assurance

```bash
# Run all backend unit, integration, and security tests + frontend typecheck
./scripts/test

# Run linters and code format checkers (ruff & eslint)
./scripts/lint

# Build production assets
pnpm --filter @ai-qa/web build
```

---

## Security & Path Integrity

- Workspace operations are restricted strictly to `runtime/workspaces/<id>`.
- Any path traversal (`../`, absolute paths, symlink escapes) will trigger a `SecurityException` and return HTTP 400.
- Runtime databases and test workspaces are excluded from Git commits via `.gitignore`.
