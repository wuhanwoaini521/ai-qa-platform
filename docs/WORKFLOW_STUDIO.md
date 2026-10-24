# Versioned QA Workflow Studio

Updated for RC Hotfix 2. A workflow definition is data; TaskRuntimeService remains the only
scheduler and execution owner. Published Workflow execution is enabled only for a verified,
server-compiled failure analysis subset described below.

## 1. Definition vs execution

| Concern | Store | Owner |
|---|---|---|
| What a workflow *should* do | `workflow_definitions` + `workflow_definition_versions` | this feature |
| What a run *did* | `agent_tasks`, `agent_task_steps`, `agent_task_events` | TaskRuntimeService |
| What a run *called* | `ai_invocations` | AIRepository |
| What a run *observed* | `discovery_evidence`, `agent_task_evidence` | Discovery evidence / task evidence |

A definition is never read back from a trace: the trace records what happened, a definition records
what was asked for. The execution diff joins the two by step `tool`, never by guessing from labels.

## 2. Versioning

- `POST /api/projects/{id}/workflows` creates the definition and its `v1` draft.
- `PUT /api/workflows/{id}/draft` writes the draft. It takes `base_checksum`; a mismatch is a `409`
  (optimistic concurrency, the same pattern as `quality_discovery_runs.version`).
- `POST /api/workflows/{id}/publish` validates, then writes a `PUBLISHED` row and opens the next
  draft. A published version is immutable; edits after publishing land in the next draft.
- `POST /api/workflows/{id}/versions/{version}/restore` copies an old version into the draft.
- `GET /api/workflows/{id}/compare?base=&head=` returns `{nodes:{added,removed,changed}, edges:{…},
  identical}` — the same shape the editor renders.

Every version stores `graph`, `issues` and a `checksum` of the graph content.

Node `position` is stored in the graph and is **not** part of the graph's meaning: `sameGraph` ignores it
(so a drag never shows up in a version diff) while `sameLayout` tracks it, and the editor counts either
kind of change as unsaved work. Without that split a dragged arrangement could never be saved — the save
button stayed disabled because the graph was "unchanged". Acceptance check *a dragged card stays where it
was put after a reload* pins both halves.

## 3. The node catalogue

`packages/project-model/project_model/workflow_definition.py` holds `CATALOGUE`: 25 node kinds, each
with `risk` (`READ` / `PROPOSE` / `APPROVAL` / `WRITE` / `EXECUTE`), `writes`, typed `inputs` and
`outputs`. A graph may only use these kinds — there is no shell, no Python, no free-form tool name.
`validate_graph` reports `EMPTY_GRAPH`, `TOO_MANY_NODES`, `INVALID_KEY`, `DUPLICATE_KEY`,
`UNKNOWN_KIND`, `MISSING_INPUT`, `INVALID_INPUT`, `UNKNOWN_INPUT`, `INPUT_TOO_LONG`,
`UNKNOWN_EDGE_NODE`, `SELF_EDGE`, `CYCLE`, `WRITE_WITHOUT_APPROVAL`, `APPROVAL_WITHOUT_WRITE`.

An invalid draft may be **saved** (the issues travel with it so the editor can show them); it cannot
be **published** — `POST /publish` answers `422` with the issue list.

## 4. Permissions

- Read: `PROJECT_READ` + project ACL (`enforce_project_access`, a stranger gets `404`).
- Edit drafts: `Permission.AUTOMATION_EDIT` (`Rule("/api/workflows", …)`).
- Publish: `Permission.PROJECT_WRITE`, checked per route. `QA_ENGINEER` can edit but not publish;
  `QA_LEAD` and `ADMIN` can publish.

## 5. Execution diff

`GET /api/workflows/{definition_id}/execution-diff?task_id=` compares the definition's draft with a
real task and returns rows `MATCHED` / `NOT_EXECUTED` / `UNDECLARED` / `FAILED` / `CANCELLED` /
`SKIPPED` / `RETRIED` plus `totals` and an explicit `unknown` list
(`step_inputs_are_not_compared`, `step_dependencies_are_not_compared`,
`a_repeated_kind_is_matched_in_step_order`). It never invents a missing fact: a step whose evidence is
absent is reported as unknown, not as success.

## 6. Verified published Workflow execution subset

`POST /api/workflows/{definition_id}/execute` starts a task through the existing `TaskRuntimeService`
for an immutable published version. The server checks project access and `RUN_EXECUTE`, resolves the
published version, verifies its graph checksum and launch inputs, validates referenced failures against
the Workflow project, and compiles the execution plan on the server. The client cannot submit a plan.

Only these shapes are enabled:

- one `failure.collect` node; or
- one `failure.collect` node followed by one `failure.classify` node, bound to the collector result.

The collector may use an authored custom key; its result is mapped explicitly to the existing
classifier handler input. Workflow tasks persist the execution ID, definition ID, published version row
ID and number, checksum, idempotency key, and request fingerprint. Replays for the same definition,
caller, and key return the same task when the fingerprint matches; reuse with different inputs or a
newly resolved published version conflicts. Task duration uses `agent.max_runtime_seconds`, and launch
is refused when `agent.enabled` is false. Workflow steps have zero retries, replans, and AI-call budget.

This is a restricted verified execution subset. It does not authorize arbitrary DAG execution and does
not establish a generic `DAG_EXECUTION_PASS`. Other catalogue kinds remain unavailable to this execution
route until their handlers and safety controls are separately verified. No arbitrary code, provider,
browser, source-write, repair, or domain-mutation handler is enabled here.

The existing scheduler, leases, cancellation, recovery, pause behavior, and Execution Trace remain the
runtime authorities. The exact persisted task and published provenance are displayed in the existing
Execution Tree.

Other editor gaps remain: no drag-to-reorder dependencies beyond connecting handles, no multi-select,
no comments, and no per-node permissions.

## 7. Verdicts

| Level | Verdict | Evidence |
|---|---|---|
| A. Definition (create, validate, version, publish immutably) | **PASS** | `apps/api/tests/test_workflow_definitions.py` (10), acceptance checks 1–12 |
| B. Editor (in-canvas edit, connect, inputs, undo/redo, save, reload, compare, phone) | **PASS** | `.ai-runs/overnight-delivery/rounds/r17-acceptance.json` 20/20, `apps/web/tests/workflow-editor-model.test.mjs` (10) |
| C. Restricted published Workflow execution | **PASS for the verified subset only** | `apps/api/tests/test_workflow_execution.py`, `apps/api/tests/test_workflow_definitions.py`, `apps/api/tests/test_runtime_migrations.py`; real Chromium acceptance `.ai-runs/rc-hotfix2-live-acceptance/` (HTTP 202, both custom-key steps completed, provenance in Execution Trace, no page errors). This does not imply arbitrary `DAG_EXECUTION_PASS`. |

## 8. Remaining execution scope

- Expanding the enabled node set requires a separate handler and safety review for each kind. The
  current launch path remains restricted to `failure.collect` and optional `failure.classify`.
- The execution diff is the data a future "definition drift" report needs; it already reports
  `UNDECLARED` steps honestly.

## 9. A workflow planned from a sentence (Round 19)

`POST /api/projects/{project_id}/workflows/plan` takes `{"prompt": "..."}` (3–2000 chars) and returns a
candidate, never a definition:

```json
{"summary": "...", "graph": {"nodes": [...], "edges": [...]},
 "issues": [], "valid": true, "invocation_id": "...", "provider_note": "..."}
```

Rules that make the candidate safe to trust:

1. **The catalogue is the only vocabulary.** The prompt sent to the model lists the 25 kinds with
   their risk, inputs and outputs. A kind outside `CATALOGUE` is dropped and reported as
   `UNKNOWN_KIND`; the candidate is then `valid: false` and cannot be published.
2. **The server validates, the model does not grade itself.** `validate_graph` from
   `packages/project-model/project_model/workflow_definition.py` produces every issue code the editor
   already knows (`MISSING_INPUT`, `CYCLE`, `WRITE_WITHOUT_APPROVAL`, …). A model that returns `"valid": true`
   in its own JSON is ignored on that field.
3. **Nothing is created.** Planning writes no definition, no version, no task and no run: the response is
   a proposal. `apps/api/tests/test_workflow_planner.py::test_planning_leaves_the_project_untouched`
   asserts the definition list is unchanged.
4. **A human still does the two irreversible things.** `PUT /draft` saves what the person accepted;
   `POST /publish` is the approval gate. The editor's `把候选放到画布` only fills the canvas, and the
   existing save/publish buttons stay unchanged.
5. **No provider, no plan.** With no real provider configured the route answers `503` with a reason;
   a model error answers `502` with the provider's error. A failed plan never leaves a definition behind.

What planning deliberately does not do: it does not choose a definition to plan into, does not overwrite
an existing draft, does not execute the proposed graph directly, and does not "repair" a prompt into a
supported one silently; an unsupported request produces a plan without the unsupported kind and the
issues that explain why. Execution still requires a person to save and publish a supported graph before
using the restricted launch route in §6.

Evidence: `.ai-runs/overnight-delivery/rounds/r19-acceptance.json` — 15/15 with the real provider
(planning took 19 s, 9 nodes, each with a stated rationale, `valid: true`), the shell request produced no
shell node, save→publish→reload kept the graph, the published checksum never changed afterwards, and the
phone viewport had no overflow.

## 11. Test-data governance (added in the Round 17 re-audit)

Acceptance runs exercise the **real** approval path, so they leave real rows behind. There are two
distinguishable kinds and neither is deleted automatically:

- **Workflow definitions / versions / tasks.** A definition is only created by the acceptance when the
  script names it (`qd_r17_acceptance`, `qd_r19_acceptance`, …). The edit-and-publish chain creates **no**
  task and no run — asserted by the acceptance (`tasks_before == tasks_after`).
- **Test cases created by an approved AI reading.** `DiscoveryIntelligenceService._create_case` stamps every
  case it creates with `tags = ["discovery", "ai-suggestion", "candidate-gap", "suggestion:<suggestion_id>"]`.
  The last tag names the exact reading that produced the case, so acceptance-created cases are findable
  without guessing from the title:

  ```bash
  curl -s "$API/api/test-cases?project_id=proj_golden_shop_v1" -H "Authorization: Bearer $TOKEN" \
    | jq '.items[] | select(.tags | index("ai-suggestion")) | {id, title, tags}'
  ```

  In the golden demo project the acceptance of Round 16 left `tc_fc72509f37fd` and `tc_e5cbf1e12f6b`.

- **Cleanup is id-scoped, never tag-scoped.** Deleting by tag would remove real cases a person approved for
  a real gap. The supported procedure is to read the ids above, confirm they are acceptance artifacts, and
  delete exactly those (`DELETE /api/test-cases/{id}`) — the coverage number is computed from the remaining
  cases, so nothing needs recomputing.
- **Coverage does not special-case these rows.** An approved suggestion *is* coverage: a person read the
  evidence and asked for a case. Excluding it from coverage would understate the product. What must not
  happen is a **fixture** case entering coverage, which is why acceptance writes its fixtures into
  `runtime/workspaces/<project>/…` files rather than into the case table.
