# Skyvern — P0 framework record

- **Knowledge Status:** VERIFIED for tag/release/license/manifest/docs metadata only; platform behavior and legal/commercial applicability are NOT TESTED/REVIEWED.
- **Topic:** AI browser automation SDK, Playwright-compatible actions, and self-hosted workflow service.
- **Research Question:** Does Skyvern materially improve browser action/extraction/validation beyond the current BrowserRuntime/Task Runtime, and what deployment, compatibility and license constraints apply?
- **Source URL(s):** [latest release metadata](https://api.github.com/repos/Skyvern-AI/skyvern/releases/latest); [release v1.0.56](https://github.com/Skyvern-AI/skyvern/releases/tag/v1.0.56); [tagged README](https://github.com/Skyvern-AI/skyvern/blob/v1.0.56/README.md); [tagged pyproject.toml](https://github.com/Skyvern-AI/skyvern/blob/v1.0.56/pyproject.toml); [tagged LICENSE](https://github.com/Skyvern-AI/skyvern/blob/v1.0.56/LICENSE); [official docs](https://www.skyvern.com/docs/); [official self-hosting docs](https://www.skyvern.com/docs/developers/self-hosted/overview).
- **Source Version:** v1.0.56, published 2026-10-14 (GitHub latest-release endpoint, retrieved 2026-10-28).
- **License:** AGPL-3.0 at tag v1.0.56. This is a material legal review trigger; it is not an automatic legal conclusion about a specific use.
- **Verified Date:** 2026-10-28.

## Findings

- The tagged manifest declares Python `>=3.11,<3.15`, Playwright `>1.46.0` for Python `>=3.12`, and FastAPI `>=0.136.1,<0.137` in its primary dependencies. Python 3.13 is within the declared range, and the Playwright range does not itself conflict with 1.62.0, but no dependency-resolution or runtime test was performed. The FastAPI ceiling conflicts with this platform's inspected installed/locked FastAPI 0.141.1; installing both into the same environment would not satisfy both declarations. A separate server/container may isolate dependencies but introduces a separate runtime boundary.
- The tagged README advertises a Playwright-compatible SDK and Docker Compose deployment with PostgreSQL. Official self-host docs (read 2026-10-28) list pip/local-server, Docker Compose and Kubernetes paths; the pip server path requires an LLM provider/key, installs Chromium, configures the database and writes a local API key into `.env`. It can start PostgreSQL via Docker or use SQLite with `--no-postgres`; the local server has no web UI, while Docker Compose adds PostgreSQL, API/browser, UI/artifact services and local artifact/recording directories. The docs state a Python 3.11–3.14 range for the pip server. Hosted service is a separate option. These are deployment instructions, not evidence of safe setup or acceptance in this platform.
- Model/provider cost, local resource consumption, and total deployment cost were not measured. Hosted service charges are not inferred.

## Limitations

No source was installed or executed; no source-level behavioral paths, local server, database, Playwright contract, token usage, or benchmark was validated. The license file is identified, but legal/commercial embedding, distribution, and network-service obligations have not been assessed. Self-hosting this system would overlap browser sessions/actions, task execution/state, provider configuration, and evidence ownership in `BrowserRuntime`, `TaskRuntimeService`, and `DecisionService`.

## Applicability

Use only as an isolated comparison candidate and only after legal review and a specific browser validation need. Do not embed the standalone server/workflow builder as a second production scheduler/browser owner. Current recommendation: **DEFER adoption; do not add production dependencies**.

- **Evidence:** release metadata; tagged README, pyproject and AGPL license; official docs read on 2026-10-28; current platform Python/Playwright constraints in `apps/api/pyproject.toml` and resolved FastAPI evidence in the architecture report; no Skyvern execution.
- **Confidence:** High for tag, license file and manifest constraints; Medium for upstream-described functionality; Low for project compatibility/value; legal impact UNKNOWN until counsel reviews the deployment/use case.
- **Related Projects:** AI QA Platform; BrowserRuntime/Playwright; Skyvern self-hosted and hosted products.
- **Next Review Condition:** Legal/compliance review before any incorporation; test dependency isolation and a disposable same-site benchmark only if a concrete gap remains; refresh tag and license immediately before PoC/decision.
