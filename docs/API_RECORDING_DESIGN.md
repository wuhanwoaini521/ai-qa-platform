# API recording & API cases — design notes (2026-11-01)

> Status: first slice implemented. This document records the reference points and the decisions taken,
> including what was deliberately not built.

## 1. Problem

The recorder only produced UI cases. Two gaps:

1. Recording a browser flow also exercises XHR/fetch calls, but nothing surfaced them.
2. The product had no way to author or run API cases at all.

## 2. Reference points (open-source)

Earlier in this session external network access was blocked; it is reachable again, so the cURL-import
and variable conventions below are checked against Bruno's published material:
[curl → GUI](https://blog.usebruno.com/curl-to-gui-import-curl-commands).

| Project | Principle worth copying |
|---|---|
| HttpRunner / `har2case` | Capture HAR → generate runnable pytest cases; case-as-code; one runner for UI and API; variables per environment |
| Bruno | Collections live as plain files in the repo (git-friendly), no cloud account, explicit request specs |
| Hoppscotch | Request builder UX: method/URL/headers/body/assertions in one panel, environment substitution |
| Playwright HAR | Network capture belongs to the browser session itself, not a separate proxy |
| Schemathesis | Generate cases from OpenAPI contracts (property-style) — future direction |

Common thread: **capture is a property of the execution session, cases are code in the repo, secrets live
in the environment, and one deterministic runner owns PASS/FAIL.**

## 3. What was built (slice 1)

1. **Capture in the existing browser runtime** (`apps/api/app/adapters/playwright/browser_runtime.py`)
   - XHR/fetch entries now record `resource_type`, request headers (safe allowlist; credential headers
     keep only their name), request body (redacted, truncated) and response content-type.
   - No new proxy, no second capture path: the recorder session already owned this list.
2. **Recorder API surface** — `GET /api/recorder/sessions/{id}/api-calls` filters to XHR/fetch, dedupes by
   `(method, url, status)`, redacts URLs and returns the bounded list.
3. **API case compiler** (`apps/api/app/services/api_case_service.py`) — `POST /api/api-cases/compile`
   turns a request spec into a pytest `httpx` case:
   - `QA_BASE_URL` override with the project SUT as the default (relative paths supported)
   - secret headers substituted from `QA_API_SECRET_*` (never printed)
   - assertions: status, JSON path (dotted + `[n]`), body contains
4. **API workbench UI** (`/http-workbench`) — request builder, header/assertion rows, live code preview,
   save to workspace, run through the existing `TestRun` path, and "从录制导入" (paste a recorder session
   id, pick a captured call, prefill the request).
5. Tests: 8 backend compiler/capture tests, 5 frontend model tests.

## 4. Deliberate non-goals (this slice)

- No API-case database table: the case is a file in the workspace plus the existing run/evidence records.
- No new execution engine or HTTP proxy.
- No automatic HAR parsing yet.
- No response-schema assertions yet (only exact value checks).

## 4b. cURL import and variables (implemented after the first slice)

Following Bruno's documented cURL import:

- supported: `-X/--request` (`-XPOST` normalized), `-H/--header`, `-A`, `-d/--data/--data-raw/--data-ascii/
  --data-urlencode`, `--data-binary @file` (path only), `--json` (sets JSON content type and promotes
  GET/HEAD to POST), `-u/--user` (Basic auth), `-b/--cookie`, `-G/--get` (moves data into the query),
  `-I/--head`, scheme-less URLs, ANSI-C `$'…'` strings from “Copy as cURL”
- intentionally ignored (connection concerns, like Bruno): `-L`, `-k`, `-o/-O`, `-x/--proxy`,
  `--max-time`, `--connect-timeout`, `--retry`, `-v`, `--compressed`, `--cert/--key/--cacert`
- variables: `{{name}}` substitution before compilation; undefined names are reported instead of being
  sent literally. Basic auth is stored as a `QA_API_SECRET_AUTHORIZATION` reference, never as a literal.

## 5. Roadmap

1. Recorder UI tab that lists captured API calls inline and saves UI+API cases together.
2. HAR import (Playwright `--save-har`) into the same compiler.
3. OpenAPI import; contract-level assertions and Schemathesis-style generation.
4. API case ↔ acceptance-criterion binding (reuse `/flows/bind-case` assertions model).
5. Auth flows: capture login request → store token as `QA_API_SECRET_*` reference.
