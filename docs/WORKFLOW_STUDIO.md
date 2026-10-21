# Versioned QA Workflow Studio

Round 17. What a workflow definition is, what it is not, and where the boundary to the
TaskRuntime sits. The definition is data; the runtime is the only thing that executes.

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

## 6. What this round deliberately does not do

- **No execution of a published definition.** `compile_plan()` produces `TaskStepSpec` rows that the
  existing runtime already understands, but nothing in the product creates a task from a definition
  yet. Round 17 verdict for `DAG_EXECUTION` is therefore **BLOCKED**, not PASS — see §7.
- No drag-to-reorder dependencies beyond connecting handles, no multi-select, no comments, no
  per-node permissions.
- No arbitrary code nodes, no expression language, no retry policy editor (each kind carries its own
  runtime defaults).
- No definition-derived scheduling: the runtime still builds plans from `build_plan(task_type)`.

## 7. Verdicts

| Level | Verdict | Evidence |
|---|---|---|
| A. Definition (create, validate, version, publish immutably) | **PASS** | `apps/api/tests/test_workflow_definitions.py` (10), acceptance checks 1–12 |
| B. Editor (in-canvas edit, connect, inputs, undo/redo, save, reload, compare, phone) | **PASS** | `.ai-runs/overnight-delivery/rounds/r17-acceptance.json` 20/20, `apps/web/tests/workflow-editor-model.test.mjs` (10) |
| C. DAG execution from a definition | **BLOCKED** | `compile_plan` exists and is tested, but no endpoint starts a task from a definition; declaring it PASS would require a scheduler path that does not exist |

## 8. Round 18+ entry points

- Starting a task from a published version needs: a `workflow_definition_version_id` on the task,
  a compile step in `TaskCommandService`, and a lease so two workers cannot run the same version's
  task twice (Round 18).
- The execution diff is the data a future "definition drift" report needs; it already reports
  `UNDECLARED` steps honestly.
