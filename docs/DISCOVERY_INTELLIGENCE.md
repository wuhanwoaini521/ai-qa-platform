# Discovery Evidence Intelligence (Round 16)

AI/Jev analysis of the scenarios the deterministic matcher could not settle, kept as a separate,
reviewable suggestion layer on top of Round 15's captured evidence.

## 1. Where it sits

```
quality_discovery_runs (Run 15)          discovery_evidence        (Run 15)
        │                                        │
        └── discovery_scenarios  ── deterministic match ──► COVERED / CANDIDATE_GAP / UNDETERMINED
                        │                                        (never rewritten by AI)
                        ▼
              discovery_suggestions  ◄── AI analysis + Jev grade (Run 16)
                        │
                        └── review gate ──► ACCEPTED / REJECTED / LINKED / CASE_CREATED / REANALYZE_REQUESTED
                                                     │
                                                     └── (only when approved) a case via TestCaseService
```

The deterministic verdict stays in `discovery_scenarios`. Everything the model says lives in
`discovery_suggestions` with its own status, so a refresh of the rule layer can never overwrite an AI
reading, and an AI reading can never overwrite a rule verdict.

## 2. Data model

`discovery_suggestions` (migration `0017_discovery_suggestions`, down-revision
`0016_discovery_evidence`; `downgrade` drops the table, the AI layer is additive):

| column | meaning |
| --- | --- |
| `suggestion_id` | stable id over `scenario_id` + `input_hash` (`sugg_<sha16>`) |
| `scenario_id` | the `discovery_scenarios` row this reading is about |
| `source` | always `ai` today; the column exists so a human note can never be mistaken for a model answer |
| `provider`, `model` | what actually answered |
| `analysis_status` | `COMPLETED` `FAILED` `REJECTED` `DEGRADED` `INSUFFICIENT_EVIDENCE` |
| `review_status` | `PENDING` `ACCEPTED` `REJECTED` `LINKED` `CASE_CREATED` `REANALYZE_REQUESTED` |
| `input_hash` | sha256 of scenario + rule verdict + cited evidence + candidate cases + provider + model + prompt version + reanalysis token |
| `attempts` | how many times the same input was asked (idempotency evidence) |
| `evidence_ids` | only ids that exist in `discovery_evidence` for this run |
| `related_case_ids` | only ids that exist in `test_cases` for this project |
| `payload` | the accepted reading (see §3) |
| `jev` | the grading record (§4) |
| `review` | decision, operator, comment, timestamp, created case |
| `task_id`, `invocation_id` | execution trace (§7) |
| `duration_ms`, `input_tokens`, `output_tokens`, `token_source` | only values the provider really reported |
| `error_type`, `error_detail` | why an analysis did not produce a reading |

Unique `(run_id, scenario_id, input_hash)` makes a repeated request idempotent; `attempts` counts it.

## 3. The reading

`DiscoveryScenarioAnalysis` (`packages/qa-core/qa_core/ai/models.py`) is the response schema:
`is_gap`, `summary`, `reasoning`, `evidence_ids`, `related_test_case_ids`, `suggested_title`,
`suggested_steps[]`, `uncertainty`, `needs_human_review`, `risk`.

Prompt: `DISCOVERY_SUGGESTION_PROMPT` (`prompt_id=discovery_suggestion`, `version=v1.0`), which is
registered in `PROMPT_REGISTRY` and therefore versioned in the record.

Every field the model may only answer with a reference is checked against the database:

| model answer | check | outcome when it fails |
| --- | --- | --- |
| `evidence_ids` | must be a subset of the ids this scenario may cite (real rows of this run) | `REJECTED` / `UNKNOWN_EVIDENCE`, nothing stored |
| `related_test_case_ids` | must exist in this project | `REJECTED` / `UNKNOWN_TEST_CASE` |
| free text | stored as given, marked `source: ai` | — |

The prompt input is bounded (`MAX_EVIDENCE_PER_PROMPT = 12`, `MAX_CASES_PER_PROMPT = 12`,
`MAX_SCENARIOS_PER_TASK = 5`), every line is redacted again with `SensitiveRedactor` before it leaves
the process, and the truncation is stated to the model (`truncated: true`) instead of hidden.

## 4. Grading, and what each status means

`jev` is written for every completed reading:

```
{"source": "jev" | "rules", "status": ..., "score": 0.505, "confidence": 0.9,
 "calibrated": false, "rule_grade": "thin", "grade": "thin",
 "rules": {"evidence_rows": 4, "kinds": [...], "associated_requests": 1, "truncated": false},
 "reason": null}
```

| status | meaning | `source` |
| --- | --- | --- |
| `JEV_GRADED` | Jev answered above the configured confidence floor | `jev` |
| `JEV_LOW_CONFIDENCE` | Jev answered, confidence below `jev.minimum_confidence` | `rules` |
| `JEV_TIMEOUT` | Jev timed out | `rules` |
| `JEV_FALLBACK` | Jev failed for another reason (recorded in `reason`) | `rules` |
| `JEV_UNAVAILABLE` | no provider answered at all | `rules` |
| `NOT_REQUESTED` | analysis did not complete, so nothing was graded | `rules` |

`calibrated` is always `false`: the number is a model output, not a measured probability.
The rule grade (`insufficient` / `thin` / `sufficient`) is computed from the deterministic facts
(`evidence_rows >= 3`, at least one associated request or two evidence kinds, not truncated) and is
kept next to every Jev number so the two can be compared.

Jev's own scale is an *expected index*, not a value: asking for three criteria returns `0..2`
(observed `1.17`). `JevDecisionProvider._rescale` maps it back onto `0..1`, so a score of `0.505`
means "halfway up the scale the platform asked for". Before Round 16 this arithmetic mistake made
every scoring call fail as `invalid_request` (Round 12's `FALLBACK` trail).

## 5. Budgets and idempotency

- Per task: `TaskAIService.reserve_ai_call` (task `max_ai_calls`), and the process-wide
  `AIBudgetGuard` for daily requests/tokens.
- Per run: at most `MAX_SCENARIOS_PER_TASK = 5` scenarios per task; the task only sees
  `CANDIDATE_GAP` / `UNDETERMINED` (or the explicit `scenario_ids` a caller asked for).
- Same scenario + same evidence + same provider/model + same prompt version → same `input_hash`:
  the existing row is updated, `attempts` increments, no second model call is charged for a page
  reload.
- An explicit `REANALYZE` review or a `reanalyze_token` on `POST .../intelligence` changes the hash,
  so a deliberate second opinion is stored as a second row instead of overwriting the first.
- No timeout inflation: the model call uses the provider's configured timeout and surfaces
  `timeout` as `JEV_TIMEOUT` / `FAILED` instead of retrying forever.

## 6. API

| endpoint | purpose |
| --- | --- |
| `POST /api/discovery/runs/{run_id}/intelligence` (202) | start (or reuse) an `ANALYZE_DISCOVERY` task |
| `GET  /api/discovery/runs/{run_id}/suggestions` | readings, newest first |
| `GET  /api/discovery/runs/{run_id}/suggestions/summary` | counts by analysis/review/grade source |
| `GET  /api/discovery/runs/{run_id}/suggestions/{suggestion_id}` | one reading + its real evidence + real cases |
| `POST /api/discovery/runs/{run_id}/suggestions/{suggestion_id}/review` | `ACCEPT` `REJECT` `LINK_CASE` `APPROVE_CREATE_CASE` `REANALYZE` |

All of them keep the existing run/project ACL (`discovery_run_access` + `project_query_access`) and
`Permission.RUN_EXECUTE` for writes. A live `ANALYZE_DISCOVERY` task for the same run is reused
instead of creating a second one.

## 7. Task execution and traceability

`TaskType.ANALYZE_DISCOVERY` runs on the existing runtime (no second state machine):

```
collect  (discovery.collect_gaps)   → read run, scenarios, evidence, cases
analyze  (discovery.analyze_gaps)   → one AI call per unsettled scenario
grade    (discovery.grade_gaps)     → rule grade + Jev score
finalize (discovery.summarize_gaps) → counts for the task record
```

Each AI call is an `ai_invocations` row with `task_id`, `run_id` (the discovery run), provider, model,
tokens and duration; each reading stores the `invocation_id` it came from and the `task_id` that
produced it. That is the whole current trace.

### Round 16.5 — Agent Execution Tree mapping

| tree field | available today | source |
| --- | --- | --- |
| `task_id` | yes | `discovery_suggestions.task_id`, `agent_tasks.id` |
| `parent_task_id` | **no real parent/child relation** | tasks are created independently; `agent_tasks` has no parent column and child runs are linked through outputs, not a hierarchy |
| `invocation_id` | yes | `discovery_suggestions.invocation_id` ↔ `ai_invocations.id` |
| `provider` / `model` | yes | `ai_invocations.provider/model` |
| `started_at` / `finished_at` | yes | `ai_invocations.started_at` + `duration_ms`; tasks have `started_at`/`finished_at` |
| `status` | yes | `ai_invocations.status` (`SUCCESS`/`FAILED`/`FALLBACK`/`CANCELLED`/`INTERRUPTED`) |
| `token_usage` | yes, when reported | `input_tokens` / `output_tokens` + `token_source` |
| `cost` | **no** | no price table exists; deriving it would be invented data |
| `evidence_ids` | yes | `discovery_suggestions.evidence_ids` |

So a tree can be drawn for *task → invocations → evidence* with honest edges from now on. A true
`parent_task_id` needs a column and a relation that the runtime does not create today; inventing one
in the UI would misrepresent the execution, so Round 16.5 must add it at the runtime level first.

## 8. UI

`apps/web/src/features/canvas/IntelligenceSection.tsx` renders inside the existing discovery node
detail in the workflow canvas — no separate page:

- counts: readings, pending review, accepted, rejected, Jev graded / degraded;
- per reading: title, summary, rule verdict, Jev status + grade, review status, cited evidence count,
  related cases, and always a "source: AI" marker;
- actions: accept, reject (with a required reason), link an existing case, approve case creation,
  request reanalysis;
- "view cited evidence" loads the real evidence rows through the Round 15 endpoint.

## 9. Limits kept honest

- Only `CANDIDATE_GAP` / `UNDETERMINED` scenarios are analysed by default; `COVERED` scenarios are
  never re-litigated by the model.
- A role/kind-only locator value (`button`, `link`, `textbox`, …) is not used to prove coverage — it
  matches almost every case. The accessible name is used instead (`GENERIC_LOCATOR_VALUES`).
- An insufficient-evidence scenario produces `INSUFFICIENT_EVIDENCE` without a model call: "we do not
  know" is a result, not a failure.
- `DEGRADED` (provider fell back) stores no reading text at all, so a fake provider can never author a
  suggestion.
- Approving case creation writes a normal test case through `TestCaseService`; it does not touch
  automation source, and the existing Studio flow takes over from there.
- Review history is stored per suggestion. It is not fed back into the deterministic matcher or into
  provider parameters: a rejection records a human decision, it does not silently retrain anything.
