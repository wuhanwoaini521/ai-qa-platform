# Central runtime configuration

`config/config.yaml` is the production runtime policy source. API and worker processes load the same `platform-config` schema at startup. `apps/api/app/settings.py` only provides a read-compatible test adapter; new runtime code uses `get_config()`. `qa-core` receives explicit policy and provider arguments and never opens YAML.

Secrets stay out of the YAML file. Secret fields must be empty or use `${ENV_NAME}` / `${ENV_NAME:-default}` references. The loader rejects literal secret values and database URLs containing inline credentials. `.env` is loaded from the repository root for local development; deployment systems can inject the same environment variables directly.

## Configuration sections and consumers

| Section | Main consumers |
| --- | --- |
| `app` | authentication, workspace and artifact storage |
| `api` | CORS and the API module entrypoint; bind and CORS changes require restart |
| `database` | SQLAlchemy engine and pool construction; URL changes require restart |
| `ai` | AI provider registry, completion timeout/retries, shared request and daily budgets, per-run budget guard |
| `jev` | Decision Settings, Jev HTTP provider, confidence acceptance, repair trust gate and fallback policy |
| `repair` | automatic start after failure, repair mode, attempt ceiling, Jev requirement and rollback policy |
| `browser` | Playwright launch, proxy, navigation/action/session timeout, viewport and locale |
| `run` | default local run timeout and worker parallel-run cap |
| `pytest` | API and worker timeout, worker count and default pytest arguments |
| `agent` | task step/retry/runtime/AI-call limits, browser action/candidate limits and Jev requirement |
| `failure` | automatic Failure record creation, screenshot/DOM/console/network capture and context limits |
| `evidence` | bounded screenshot, console, network and page-control evidence |
| `recorder` | recorder enablement, candidate count and preferred fallback locator strategy |
| `debugger` | adapter startup, initial attach and shutdown timeouts |
| `worker` | API URL/token, worker identity/capabilities/concurrency/polling and storage directories |
| `integrations` | enablement and credentials/URLs for GitHub, Jira, TestRail and Jenkins |
| `logging` | root logger level |
| `features` | AI repair, Jev decisions, automatic repair, recorder, debugger and live browser telemetry |

Secret values are redacted from diagnostics. `logging.redact_secrets` is intentionally not configurable: redaction is a security invariant. High-risk task plans continue to require approval as a product safety invariant.

## Inspecting and reloading

```powershell
uv run --package api python -m platform_config check
uv run --package api python -m platform_config dump --effective
```

`check` validates the schema and reports whether AI/Jev are disabled, simulated, configured or blocked by a missing key. `READY_CONFIGURED` means required settings are present; it does not claim that an external provider is reachable. Use the Settings page connection checks for that. `dump --effective` redacts every typed secret.

The authenticated Settings API exposes `GET /api/settings/effective`, `GET /api/settings/sources` and `POST /api/settings/reload`. Reload validates a complete candidate before replacing the active immutable snapshot. Invalid config leaves the last good snapshot active. Compose mounts `./config` read-only into API and worker containers, so host edits are visible to API reload. API bind/CORS, database engine/pool settings, application paths/secret, and worker process settings require a process restart.

AI/Jev Settings endpoints are read-only runtime views. Their legacy write endpoints return `409`; old AI/Jev ORM rows are detected and shown as migration notices, but are never used as runtime fallback. The database tables are retained for history. There is no automatic legacy-secret migration: copy non-secret policy to YAML and move secrets to environment variables before removing old rows manually.

## Environment precedence

The provider runtime uses this precedence: process environment (including the repository-root `.env` loaded for local development) > `config/config.yaml` > typed schema defaults. The canonical overrides are `QA_AI_ENABLED`, `QA_AI_PROVIDER`, `QA_AI_API_KEY`, `QA_AI_BASE_URL`, `QA_AI_MODEL`, `QA_AI_TIMEOUT_SECONDS`, `QA_AI_MAX_RETRIES`, and `JEV_ENABLED`, `JEV_API_KEY`, `JEV_BASE_URL`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`, `JEV_RETRIES`, `JEV_MINIMUM_CONFIDENCE`. Empty/unset optional secrets remain unconfigured; no health response treats a missing credential as a successful real provider.

Other environment values are explicit interpolation inputs in the YAML: API bind address/port, database URL, app/provider/integration/proxy credentials or URLs, and worker API URL/token/name. The worker ID is a deployment identity; if unset, it is generated per process. Docker Compose forwards all provider overrides and uses defaults matching the committed YAML.

Other environment reads are execution context rather than a second platform config: `PYTEST_XDIST_WORKER`, `PYTHONPATH`, `QA_ARTIFACT_DIR` and the live-browser event path identify a pytest child process; the onboarding collector passes selected environment into the imported project's own tools; API test fixtures use `AI_QA_TEST_DATABASE_URL`; user-authored pytest code may read its own environment. Browser proxy variables passed to a child are derived from `config/config.yaml` before the process starts.

The browser's local theme, language, landing page and default project remain browser-local user preferences. They do not control server runtime policy and are not copied into Vite environment variables.
