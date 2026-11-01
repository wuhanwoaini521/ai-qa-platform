# Controlled locator-repair loop (2026-11-01)

Goal: prove failure → proposal → human apply → exact rerun works on a real page, without new
orchestration. The only new artifacts are a throwaway fixture page and this evidence.

## Fixture

`/tmp/locator-fixture/index.html` served by `python3 -m http.server 8099`:

- `?mode=old` → `<button id="submit" data-test="submit">Save</button>`
- `?mode=new` → the `id` attribute is removed, only `data-test="submit"` remains

The test under repair is human-written and clicks `#submit` on `?mode=new`, so it times out exactly
like a real DOM change.

## Actual sequence (real API calls)

| Step | Result |
|---|---|
| Failing run | `run_96929cb88aab` **FAILED** — `TimeoutError: Locator.click ... waiting for locator("#submit")` |
| Failure record | `fail_1ccb0a1a436a`, classification **LOCATOR_CHANGED**, failing_locator `#submit` |
| Analysis (canonical `analyze/stream`) | Jev decision, confidence **1.0**, candidate verified against the captured page |
| Proposal | `#submit` → `get_by_role("button", name="Save", exact=True)`; code diff + source sha recorded |
| Human apply | `POST .../analyses/11d57934.../apply` → **200**, workflow state `PATCH_APPLIED` |
| Exact rerun | `run_26c54863eebb9aaa5cd291bca9d56578` **PASSED** on the same nodeid `tests/test_locator_repair.py::test_submit_button_saves` |

Files: `evidence/01-failure-run.json`, `evidence/02-repair-proposal-applied.json`,
`evidence/03-rerun-passed.json`.

## What this also exposed

The light `POST /failures/{id}/diagnose` path leaves a repair record in `DECIDING` forever (state
machine allows only `CANCEL`). The workflow only reaches `PATCH_READY` through
`POST /failures/{id}/analyze/stream`. Worth a product decision: either make `diagnose` complete the
decision transition, or hide/rename it so callers do not take the dead path.

## Probe data

`dev_probe_inventory.py` (extended with this batch's names) lists 8 probe projects. The product has
**no project delete endpoint**, so cleanup is non-destructive: the three probe projects created this
batch are now `hidden_from_overview=true` (verified absent from `/dashboard/stats`, present in
`/projects`). Data untouched.
