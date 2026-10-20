# Structured Discovery Evidence

Discovery already produced a run row, page states, gaps and a coverage map. This document records
the structured evidence index added underneath it: what one fact is, how it is identified, what it
may store, and what it deliberately does not.

## 1. What already existed (audit, Round 15 Phase 1)

| Source | Where | What it holds | Reused as |
| --- | --- | --- | --- |
| Run row | `apps/api/app/persistence/models.py` `QualityDiscoveryRunORM.result` | states, edges, actions, features, requirements, gaps, coverage | The projection every existing consumer reads. Unchanged. |
| Page snapshots | `apps/api/app/adapters/playwright/browser_runtime.py` (`snapshot`) | url, title, fingerprint, controls (already redacted by `_safe_controls`), `network` list (`url`, `method`, `status`, `failed`) | The raw input of capture. |
| Locator verification | `apps/api/app/adapters/playwright/locator.py::verify_locator` | `match_count`, `unique`, `visible`, `enabled`, `editable`, `clickable`, `verified` | The only source of locator uniqueness — never re-counted by hand. |
| Recorder evidence | `automation_bindings.recorder_evidence_bundle` | per-step action, locator, frame path | Not touched by this index; the Studio binding keeps reading it. |
| Network summary | `quality_discovery_execution._network_summary` | status buckets per state | Unchanged; capture reads `snapshot.network`, the raw list, not this summary. |
| Canvas projection | `apps/api/app/services/workflow_canvas_service.py` | 8 stages, node metrics, evidence index | Extended with the evidence counts (Phase 5). |

Gaps found: the run row kept only counts (`{"responses": {"2xx": 3}}`), so a single request could
not be cited; states were unaddressable beyond their id; nothing tied a request to the action that
caused it; nothing said which behaviour was covered by an existing test.

## 2. The evidence model

Two tables, both keyed by the discovery run.

`discovery_evidence` — one row per structured fact:

| Column | Meaning |
| --- | --- |
| `run_id`, `project_id` | Scope. Every row belongs to exactly one run. |
| `kind` | `dom_element`, `locator_candidate`, `network_request`, `user_action`, `page_state`, `screenshot`. |
| `evidence_id` | Stable id: `f"{prefix}_{sha256(identity)[:16]}"`. Rebuilding the same fact yields the same id. |
| `dedupe_key` | The identity used for comparison and diffing (`tag|role|name|test id|stable id|stable href`, `METHOD|url-template`, …). |
| `state_id`, `step_id`, `artifact_id` | Optional links to the page state, the action step and a stored artifact. |
| `source` | `browser_runtime` — who observed it. |
| `redacted` | Whether a value had to be rewritten before storage. |
| `payload` | The fact itself (bounded, redacted, JSON). |
| `observed_at` | When the browser saw it (not when it was written). |

Unique on `(run_id, evidence_id)`; indexed by `(run_id, kind)` and `(run_id, dedupe_key)`.

`discovery_scenarios` — the derived Evidence → Candidate Scenario → Test Case relation:

| Column | Meaning |
| --- | --- |
| `scenario_id` | `scen_<hash>` of `url_template|action|stable target`. |
| `evidence_ids` | The evidence the scenario was derived from (action, locator, element, requests). |
| `test_case_ids`, `coverage_status`, `match_method`, `note` | The match result: `COVERED`, `CANDIDATE_GAP` or `UNDETERMINED`, and why. |

Unique on `(run_id, scenario_id)`; refreshed wholesale so a re-derivation cannot leave stale rows.

### Identity rules

* Unstable values are normalised before they enter an identity: uuid → `{uuid}`, hex ≥ 8 → `{hex}`,
  digit runs ≥ 2 → `{n}`. Short numbers survive ("Size 8" is a name, not a counter).
* URL query values are replaced by `*`, the route and the port are kept: `127.0.0.1:8000` and
  `127.0.0.1:5173` are different servers and must not collapse into one template.
* An extension-less path is a page unless it sits under an `api` segment — `/api/cart` is a call,
  `/products` is a navigation. Assets are classified by suffix so they never inflate behaviour counts.

### What is never stored

* Input values (`input`/`textarea` content) — the element payload has no `value` key at all.
* Query values, request bodies, response bodies, headers, cookies, tokens.
* Credentials: a link with userinfo in it is dropped and counted as `dom_element.credentials_in_href`.
* Large binaries: a screenshot is referenced by `artifact_id` (the existing artifact store keeps the
  bytes); nothing is copied into the index.

### Budgets

| Setting | Default | Effect |
| --- | --- | --- |
| `discovery.capture_evidence` | `true` | Off: no rows are written, runs behave as before. |
| `discovery.max_evidence_records` | `6000` | Per-run ceiling; overflow is reported as `capped`, never silently dropped. |
| `discovery.max_network_evidence` | `200` | Per-run ceiling for request rows. |
| `discovery.max_payload_chars` | `2000` | Truncation limit for any single payload string. |
| `MAX_ELEMENTS_PER_STATE` | `60` | Per-state element cap. |
| `MAX_REQUESTS_PER_STATE` | `40` | Per-state request cap. |

Capture runs inside the exploration loop after the observation is already persisted, opens its own
session, and swallows its own failures into a `capture.failed` event: evidence can never fail a run.

## 3. Migration and rollback

* Revision `0016_discovery_evidence` (`apps/api/alembic/versions/0016_discovery_evidence.py`),
  parent `0015_artifact_ownership`. It only creates the two tables and their indexes.
* `downgrade` drops them in reverse order. No existing table is altered, so a rollback cannot lose
  Discovery, run, failure or artifact data — only the derived evidence index, which is re-derivable
  from a new run.
* The run row is untouched, so a downgraded deployment keeps every existing projection. Its
  capture hook then fails into a `capture.failed` event and the run continues, because evidence is
  never allowed to fail a run.
* `apps/api/tests/test_runtime_migrations.py` upgrades, downgrades to `0015_artifact_ownership` and
  upgrades again in one test, and derives the expected table count from the ORM metadata so a new
  revision does not have to re-bake a number.

## 4. Compatibility risks

| Risk | Why it is bounded |
| --- | --- |
| Extra rows per run | Two tables, bounded by `max_evidence_records`, one write per state/action. On the demo shop a 5-state/6-action run writes 35 rows. |
| JSON payload drift | The payload is a plain dict read only through the evidence API and the canvas; nothing joins on it. |
| Duplicate capture | `(run_id, evidence_id)` unique + upsert-in-place: a later capture that learns an association upgrades the stored row instead of adding a second one. |
| Revisiting a state | A state that already carries its `capture` counters is not re-indexed, so `raw` and `deduped` stay on the same side of the arithmetic. |
| Capture slow or broken | Runs in its own session, catches every error, emits `capture.failed`, and the run goes on. |
| SQLite write contention | One extra short transaction per state/action, after the run row's own write. |
| Redis/queue free | No new process, worker or scheduler: capture is a hook on the existing exploration loop. |

## 5. Metric definitions (Phase 3)

Every number is reported with the rule that produced it (`analysis.measures`), and none is inferred
by a model.

| Metric | Rule |
| --- | --- |
| `dom_element.raw` | Controls the browser reported per state, before any dedupe. |
| `dom_element.deduped` | Distinct element identities over all states. |
| `dom_element.filtered` | Dropped on purpose: credentials in the href, or the per-state budget. |
| `network_request.raw` / `deduped` | Responses per state / distinct method + URL template pairs. |
| `network_request.associated` | Requests proven to follow an action by the response-list prefix or set difference. |
| `network_request.unassociated` | Requests no action could be tied to — reported, never assumed. |
| `locator_candidate.ambiguous` | Locators whose verified `match_count` is greater than one. |
| `user_action.state_changed` | Actions whose landing fingerprint differs from the state they started in. |
| `coverage_summary.*` | `COVERED` / `CANDIDATE_GAP` / `UNDETERMINED` per scenario, with `match_method`. |

Coverage is **not** a business-coverage claim: a scenario is `COVERED` only when its stable target
appears in an existing test case's own text (target wording, or the locator value); everything else
is a candidate gap for a human or a later AI/Jev pass to confirm.

## 6. Deliberately not captured (Round 15)

* Full network bodies, headers, cookies and input values.
* Per-element screenshots (the state screenshot is referenced once).
* Visual snapshots beyond the existing artifact.
* Cross-run element lineage beyond the stable `dedupe_key` diff.
* Any semantic judgement: which behaviour matters, whether a gap is worth a test. That is Round 16's
  AI/Jev surface, and it will read this index rather than re-capture the page.
