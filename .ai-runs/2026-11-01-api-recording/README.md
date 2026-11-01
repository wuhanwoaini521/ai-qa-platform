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
