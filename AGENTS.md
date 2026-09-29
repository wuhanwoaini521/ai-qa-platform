# Agent Guidelines for AI QA Platform

## Operational Principles

- **Platform Environment**: This repository runs on macOS, Linux and Windows. Developer tasks are cross-platform Python in `scripts/task.py`; the `scripts/dev|test|lint` files are bash shims over it.
- **Path Integrity**: Use the current repository path. Do not guess filesystem paths. Run `pwd` (`Get-Location` in PowerShell) before changing directories.
- **Runtime Management**: Use `mise`-managed runtimes (`python 3.13`, `node 24`, `uv`, `pnpm`).
- **Python Tooling**: Use `uv` for Python workspace management and dependency resolution.
- **Frontend Tooling**: Use `pnpm` for frontend workspace and package management.
- **Permission Safety**: Do not invoke `sudo` for project dependencies.
- **Git Safety**:
  - Do not force push (`git push --force` or `--force-with-lease`).
  - Do not run `git reset --hard` or `git clean -fd`.
  - Protect existing user changes.
  - Prefer clean, structured, incremental commits.
  - Run relevant tests and linters before committing.
- **Architecture Boundaries**:
  - `apps/web`: React + TypeScript + Vite frontend.
  - `apps/api`: FastAPI domain services & REST endpoints.
  - `apps/worker`: Long-running QA jobs and execution workers.
  - `packages/qa-core`: Core testing contracts, fake test runners, diagnostic interfaces.
  - `packages/project-model`: Shared domain models and schemas.
  - `packages/integrations`: Connectors and integrations (future TestRail, GitHub, etc.).
  - `runtime/`: Editable workspaces, projects, and runtime artifacts (never commit runtime data).
