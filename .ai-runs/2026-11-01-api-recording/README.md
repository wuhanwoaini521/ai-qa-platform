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
