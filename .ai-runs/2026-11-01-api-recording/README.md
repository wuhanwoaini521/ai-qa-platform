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
