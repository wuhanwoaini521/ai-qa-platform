# Regression — night round 5

**Risk: HIGH.** Final regression spans API persistence/state, generated contracts, UI behavior, and the explicit source-write approval boundary.

| Area | Command / evidence | Result |
|---|---|---|
| Python / backend / worker / package suites | `pnpm test` → `mise exec -- uv run pytest` | **752 passed, 8 skipped, 0 failed** (760 collected) |
| Frontend | same `pnpm test` task | **146 passed**; typecheck, ESLint, Vite build passed |
| Static checks / translations | `pnpm lint` | Ruff, format (428 files), i18n parity (25 namespaces / 2,916 keys), ESLint passed |
| Quickstart | documented `mise exec -- uv run pytest -c examples/quickstart/pytest.ini examples/quickstart/tests -q` | **6 passed** |
| API contract | exporter `--check`; OpenAPI Typescript generated to `/tmp` and compared | Current; generated schema exact match; workspace artifacts not overwritten |
| Runtime | isolated FastAPI/Vite, ports 8002/5173; live probe and login | API live 200; web title served; login/API reads 200 |
| Golden Journey | browser Reject → reload → denied Apply/source check | Passed; reject 200; persisted `HUMAN_REJECTED`; Apply 422; source unchanged |
| UI / responsive | system Chrome; dashboard, workspace/failure, projects, runs; 1440/768/360 widths | Routes loaded; no horizontal overflow; scoped axe 0 violations / 0 incomplete |
| Repository diff | `git diff --check`, `git diff --check HEAD~2..HEAD` | Passed |
| PostgreSQL | CI PostgreSQL 16 lane / local DB URL | Not run; no test DB URL was configured |
| OS matrix | CI Windows/Linux | Not run; this environment is macOS |
| Live AI + Jev | gated live browser and locator-repair acceptance | Skipped; not authorized this round; prior-round evidence is carried forward, not re-claimed |
| Worker runtime / full requirement-to-release UI journey | no worker job or formal test execution started | Not run; this browser pass was intentionally limited to a synthetic persisted failure and approval boundary |
| Independent review | Orca | Blocked; see `08-independent-review.md` |

No regression was observed in executed checks. Eight tests remained skipped, including environment/credential-gated live AI/Jev and PostgreSQL coverage. The web build emits the existing large-chunk advisory. Full per-command output and browser evidence are in `evidence/`.
