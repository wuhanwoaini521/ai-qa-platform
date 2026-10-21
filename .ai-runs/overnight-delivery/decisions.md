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
