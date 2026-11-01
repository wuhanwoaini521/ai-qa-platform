# API recording + API workbench (2026-11-01)

Goal: recording should capture API traffic, and the product should have an API authoring surface.

## Evidence

`evidence/api-recording.json`, `evidence/api-workbench-1440x900.png`, `api-workbench-1280x800.png`.

| Step | Result |
|---|---|
| Browser recording session on `http://127.0.0.1:8099/new/` | session `36de0067680b…` created |
| Captured API calls | `GET http://127.0.0.1:8099/api/info` → `200`, content-type `application/octet-stream` |
| Compile via `/api/api-cases/compile` | `test_api_info`, assertions: status 200 + `json_path service == "fixture"` |
| Save + run | `tests/test_api_info.py::test_api_info` → **PASSED** |
| Workbench UI | request builder + live preview + recorder import list (1 call) |

## Notes

- Captured bodies/headers are redacted; credential headers keep only their names.
- Relative URLs default to the project SUT via `base_url` (override with `QA_BASE_URL` at run time).
- Page route is `/http-workbench` because the dev server proxies every `/api*` path to the backend.

## Verified

- Backend: 8 API compiler/capture tests + 25 flow/binding/compiler tests, Ruff clean.
- Frontend: 250 tests, tsc, ESLint, i18n 29 namespaces / 3,670 keys.

## Known limits

- No recorder-panel tab yet (import uses the session id).
- No HAR/OpenAPI import yet; assertions are status/JSON-path/body-contains.

---

## Round 2: capture and save API cases inside the recorder

The recorder view now has an inline **「接口调用（录制捕获）」** panel:

- polls `GET /recorder/sessions/{id}/api-calls` every 5s while a session is open
- lists method, URL and status for every captured XHR/fetch
- one click saves a pytest API case into the workspace (`tests/test_<method>_<path>.py`)

Live evidence: `evidence/recorder-api-panel-1440x900.png`,
`evidence/recorder-api-saved-1440x900.png`, `evidence/recorder-api-panel.json`.

| Check | Result |
|---|---|
| Recorded session on `/new/` | panel shows `GET http://127.0.0.1:8099/api/info 200` |
| Save button | `已保存 API 用例：tests/test_get_api_info.py` |
| File content | real pytest + httpx case (status assertion from the captured call) |
| Run it | `tests/test_get_api_info.py::test_get_api_info` → **PASSED** |

So one recording session now produces both case kinds: the UI case through the existing
「保存为用例并运行」, and the API case through this panel.

---

## Round 3: recorded API cases become real test cases

Saving a captured API call now goes through the server (`POST /recorder/sessions/{id}/save-api-case`):

- compiles the captured call to a pytest API case
- writes `tests/test_<method>_<path>.py` into the project workspace
- creates/refreshes a `TestCase` (`tc_api_<hash>`, title `API <METHOD> <path>`) with an automation
  binding to the generated nodeid
- the recorder panel shows the saved path plus a link to the new case (`打开 API 用例`)

Live evidence: `evidence/api-case-recorded-case.json`.

| Check | Result |
|---|---|
| Captured call | `GET http://127.0.0.1:8099/api/info` → 200 |
| `save-api-case` | `tests/test_get_api_info.py`, case `tc_api_7078e4bf3ab11b458535a832147f9` |
| Case + binding | title `API GET http://127.0.0.1:8099/api/info`, nodeid `tests/test_get_api_info.py::test_get_api_info` |
| Run | **PASSED** |
| Recorder UI | `已保存 API 用例：tests/test_get_api_info.py · 打开 API 用例` |

Tests: 2 integration tests for save/reuse/unknown-call, 8 compiler tests, recorder save-flow regression.

---

## Round 4: HAR and OpenAPI import (learn from har2case / Schemathesis)

The API workbench now imports real inputs instead of only hand-typed requests:

- **导入 HAR** — parses a captured HAR file, keeps XHR/fetch or JSON/GraphQL responses, dedupes by
  `(method, url, status)` and maps request headers/body/status into the same call list used by the
  recorder. Clicking a call prefills method, URL, headers, JSON body and a status assertion.
- **导入 OpenAPI** — parses an OpenAPI 3 / Swagger 2 document, lists each operation with its preferred
  2xx status, and prefills a case (path + expected status) in one click.

Evidence: `evidence/api-workbench-import-1440x900.png` (HAR calls + OpenAPI operations, POST /api/orders
prefilled with status 201 and `test_post_api_orders` generated).

| Check | Result |
|---|---|
| HAR import | 2 API calls (script entry filtered out), headers/body/status mapped |
| OpenAPI import | `GET /api/info → 200`, `POST /api/orders → 201` listed |
| One-click prefill | method `POST`, URL `/api/orders`, assertion `201`, preview generated |

Tests: 4 new parser tests (HAR filter/dedupe/mapping/errors, OpenAPI listing/status/errors); frontend
suite 254 passed; `vite build` and i18n (29 namespaces / 3,685 keys) green.

Design note: import is authoring-only. Nothing executes or writes until the human saves the case; the
same pytest/httpx compiler and runner stay the only execution path.

---

## Round 5: API cases join the case-assertion traceability

The workbench save now goes through `POST /api/api-cases/save`, which:

- compiles the request and writes the pytest file
- creates/refreshes the `tc_api_*` case with a nodeid binding
- when a requirement is selected, stores `CaseAssertion` rows (`TCA-API-…`) carrying
  `criterion_id`, `nodeid` and a `check` describing the request, so the API case appears in the same
  assertion panel as UI cases and reports run state per criterion

Evidence: `evidence/api-workbench-bound-1440x900.png`, `evidence/api-case-criteria-binding.json`.

| Check | Result |
|---|---|
| Save with requirement + AC-001 | `tests/test_get_api_info.py`, case `tc_api_4caf648facabf5c67176d9a9d0353` |
| Assertions before run | `AC-001 → NEVER_RUN` (nodeid `tests/test_get_api_info.py::test_get_api_info`) |
| Run | **PASSED** |
| Assertions after run | `AC-001 → PASSED` |

Tests: 3 persistence tests (file+case+assertions, unknown criterion 422, no requirement), plus compiler
and recorder API tests; frontend 254 tests, vite build, i18n 29 / 3,689 keys, Ruff clean.

---

## Round 6: auth tokens stay out of code; bulk save the captured API cases

### Auth capture

Recorded API cases now keep the captured request headers/body, so an `Authorization` header becomes a
`QA_API_SECRET_AUTHORIZATION` reference instead of a literal token.

`evidence/api-auth-token.json`:

| Check | Result |
|---|---|
| Captured header | `authorization: [REDACTED]` (never the token) |
| Generated code | references `QA_API_SECRET_AUTHORIZATION`, no token literal |
| Run without the env var | **FAILED** — `RuntimeError: Set environment variable QA_API_SECRET_AUTHORIZATION` |
| Run with `QA_API_SECRET_AUTHORIZATION=Bearer fixture-token` | **PASSED** |

Two real bugs surfaced and were fixed on the way:

1. the compiler rendered secret headers as a **set literal** (`{"authorization": {secret}}`), which made
   httpx reject the header value;
2. `project_subprocess_environment` filtered every `QA_API_SECRET_*` name as a credential, so the run
   environment could never supply the token. Explicit `QA_API_SECRET_*` values are now forwarded like
   recorder secrets, while ambient credentials stay filtered.

### Bulk save

The recorder API panel gained **「保存全部 API 用例」**. A fixture page with two XHR calls produced:

- entries: `GET /api/info 200`, `GET /api/stats 200`
- bulk save: `已保存 2 个 API 用例` (`evidence/recorder-api-save-all-1440x900.png`)

Tests: 25 backend (recorder API, compiler, persistence, redaction) + 254 frontend; Ruff, tsc, ESLint,
vite build and i18n green.

---

## Round 7: contract-level assertions (Schemathesis direction)

OpenAPI import now keeps the response schema and turns it into a deterministic contract check.

- Backend: new assertion kind `json_contract` with an embedded simplified schema
  (`type / required / properties / items`). The generated pytest module carries a small
  `_check_contract()` helper — no new dependency, no jsonschema package.
- Frontend: OpenAPI import extracts the 2xx `application/json` schema (simplified, depth ≤ 6, bounded),
  adds a `json_contract` assertion on "use this operation", and shows it as an editable contract row.
- Evidence: `evidence/api-contract.json`, `evidence/api-workbench-contract-1440x900.png`.

| Check | Result |
|---|---|
| Schema matches fixture | `test_api_contract_ok` → **PASSED** |
| Schema requires a missing field | `test_api_contract_bad` → **FAILED** — `$: missing required key missing_field` |
| OpenAPI import in UI | assertion kinds `['status', 'json_contract']`, contract editor present |

Tests: 2 new backend contract tests (emit+enforce, invalid schema rejected), 2 frontend parser/payload
tests; 27 backend tests, 256 frontend tests, Ruff/tsc/ESLint/vite build/i18n green.

---

## Round 8: one action saves both case kinds

Recorder header gained **「保存 UI+API 用例」**: it writes the UI script, saves the UI case, then saves
every captured API call as an API case, and renders a **保存结果** panel with links to each case.
Partial failures no longer abort the other half — they are reported in the summary.

Evidence: `evidence/recorder-merge-save-1440x900.png`.

| Check | Result |
|---|---|
| Recorded steps | 3 (one real click forwarded to the browser) |
| Captured API calls | `GET /api/info 200`, `GET /api/stats 200` |
| One click result | UI case `tests/test_recorded_case.py` + API cases `tests/test_get_api_info.py`, `tests/test_get_api_stats.py` |
| Files on disk | all three exist (2120 / 2397 / 2150 chars) |
| Summary links | both case kinds linked from the 保存结果 panel |

So the original ask — “recording produces both a UI case and an API case” — is now a single action.

Gates: 256 frontend tests, tsc, ESLint, vite build, i18n 29 / 3,701 keys, Ruff clean.

---

## Round 9: cURL import + {{variables}} (checked against Bruno's docs)

Network access came back this round, so the conventions were checked against Bruno's published
[curl → GUI](https://blog.usebruno.com/curl-to-gui-import-curl-commands) material instead of memory.

- **从 cURL 导入** in the workbench: `-X/-H/-A/-d/--data-raw/--json/-u/-b/-G/-I`, `-XPOST` normalization,
  scheme-less URLs, ANSI-C `$'…'` strings; connection-only flags (`-L`, `-k`, `-o`, proxy, timeouts,
  `--cert/--key`) are reported as ignored rather than silently dropped.
- **变量 `{{name}}`**: name/value rows resolve in URL, header values and body before compilation;
  unresolved names are listed instead of being sent literally. A URL that starts with `{{VAR}}` is kept
  intact (no forced `https://`).
- Basic auth from `-u` becomes a `QA_API_SECRET_AUTHORIZATION` reference, never a literal credential.
- Evidence: `evidence/api-workbench-curl-vars-1440x900.png` — imported `curl '{{BASE_URL}}/api/info' …`,
  variable `BASE_URL=http://127.0.0.1:8099`, preview 2,197 chars containing the resolved host.

Tests: 7 new parser/variable tests (18 in the API model file); frontend suite **263 passed**, tsc,
ESLint, vite build, i18n 29 / 3,707 keys, Ruff clean.

---

## Round 10: record → replay loop (mock the APIs of a recorded UI case)

The recorder now captures response bodies and can generate a UI case that replays them through
`page.route`, so the UI case runs on recorded API data instead of the live backend.

- Async capture: response bodies are read with `await response.body()` on the async runtime (a sync
  handler cannot); XHR/fetch text payloads are captured even when a static server serves them as
  octet-stream, bounded to 64 KiB and redacted.
- Generator: `mock_responses` produce `page.route(...)` fulfill handlers. One real bug found and fixed:
  Playwright calls the handler as `(route, request)`, so the closure parameter must be
  `lambda route, request, m=mock` — the earlier `(route, m=mock)` swallowed the request and every fetch
  failed.
- Recorder UI: the API panel has a replay toggle showing how many response bodies are available; when on,
  generation sends the captured mocks.

Live proof (`evidence/replay-loop.json`):

| Step | Result |
|---|---|
| Record with the fixture serving `service=fixture` | captured `{"service": "fixture", "count": 3}` |
| Change the server to `service=changed-live` after recording | — |
| Replay of the recorded bodies | **PASSED** (page showed `service=fixture orders=3`) |
| Same steps without mocks against the changed server | **FAILED** — actual `service=changed-live orders=3` |

UI: `evidence/recorder-replay-toggle-1440x900.png`; the intercepted generate request carried
`mock_responses` with 2 entries.

Tests: 3 mock tests (route generation + handler signature, no routes without mocks, body passthrough);
backend 16 in the affected set, frontend 263, tsc/ESLint/vite build/i18n 3,709, Ruff clean.
