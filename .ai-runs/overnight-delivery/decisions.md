# Decisions

- **Start HEAD is `c6d08df`, not `b3c1b28`.** The brief named `b3c1b28`; the repository is one commit
  ahead (`c6d08df test(e2e): keep the Round 16.5 execution tree acceptance evidence`). Facts are taken
  from the repository.
- **Round 17 storage**: two new tables (`workflow_definitions`, `workflow_definition_versions`) instead
  of reusing `agent_tasks`. A definition is authoring data; a task is execution data. Mixing them would
  make "published version is immutable" impossible to state.
- **Draft is a version row** with `state = DRAFT`; publishing flips that row to `PUBLISHED` and opens the
  next draft row. A published row is never written again, so an execution that references version *n*
  cannot be affected by later edits.
- **Stale-editor guard** is an optimistic checksum: `PUT .../draft` with `base_checksum` fails 409 when
  someone else saved in between. Two browsers can therefore not silently overwrite each other.
- **Publishing needs `PROJECT_WRITE`** (lead/admin), drafting needs `AUTOMATION_EDIT` (engineer+), reading
  needs `PROJECT_READ`. This is the "approval before publish" split, enforced by the route guard.
- **No second scheduler.** A published graph compiles into ordinary `TaskStepSpec` rows with
  `depends_on` keys; the existing `TaskRuntimeService` step loop already honours dependencies and
  approvals. Nothing in the new code starts work.
- **Node kinds are a closed whitelist** with declared inputs; validation rejects unknown kinds, cycles,
  missing/unknown/invalid inputs, unknown edge endpoints and a write without an approval before it.

## Round 19 — planner (2026)

- **The model proposes, the server validates.** `validate_graph` from `project_model.workflow_definition`
  is the single source of truth for `valid`; the model's own `"valid"` field is ignored. Reason: a model
  that grades itself is not a gate.
- **Planning writes nothing.** No definition, version, task or run is created by `POST /workflows/plan`;
  saving and publishing stay the two human acts already in the editor. Evidence: by API and by test.
- **An unsupported request degrades, it does not get silently rewritten.** Asking for a shell step
  yields a plan that uses only catalogue kinds plus issues explaining the gap — the visible outcome is
  "your workflow cannot include that", not a mystery.
- **DAG execution stays BLOCKED.** A planned graph can be saved and published, but no endpoint starts a
  task from a published version. Declaring Round 19 execution PASS would be false; it inherits
  Round 17 C = BLOCKED.
- **No new node kinds, no expression language, no per-node model choice.** The planner is a producer of
  candidate graphs, not a second scheduler.
