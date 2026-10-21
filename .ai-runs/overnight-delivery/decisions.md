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

## Round 20

- The PostgreSQL channel is worth its cost: it found five defects in one run, three of which are
  invisible on SQLite (column width, index naming drift, and a router collected as a test module).
  CI's `pytest apps/api` command was red while a local `pytest` was green — the difference is
  `testpaths`, so both commands are now part of the round's evidence.
- The deployment drill runs as its own compose project on spare ports with its own env file, and
  removes `container_name` so two stacks can share a host. Hard-coded names made `-p` a lie.
- Two image-level defects had to be fixed before any drill could run at all: an invalid
  `HEALTHCHECK` directive in the API Dockerfile and a literal nginx upstream in the web image.
  Both would have failed the first real deployment.
- File-level backups are verified by restoring into a second database and comparing row counts and
  the alembic revision, not by checking that a dump file is non-empty.
- CI as a service stays BLOCKED: this mission forbids pushing, and the workflow only runs on push
  to main. Parity is recorded instead of claimed.


## Round 21 — legibility beats fitting

- **A canvas that shows everything at 6 px is worse than one you pan.** The pipeline fit threshold moved from
  0.45 to a measured readability floor (0.82 desktop, 0.72 phone). The MiniMap stays as the overview and was
  shrunk to 148x92 because the default 200x150 sat on the last column.
- **The execution tree becomes a vertical list below a 720 px host** instead of four squeezed columns. Same
  parent links, same nodes; only the layout changes, and the cards take a fixed 300 px width so a long label
  cannot overflow. This is a layout rule in `executionTreeModel.treeNodes(..., {stacked: true})`, pure and
  covered by a unit test.
- **Node fit is a bounded retry, not a single attempt.** The old effect returned silently when the host was
  not mounted yet; that is why the tree stayed at zoom 1 with its last column off-screen at 1024.
- **The stress numbers come from a scaled copy of a real trace**, not from invented node shapes. The first
  attempt invented `{type, status}`-only nodes and both the panel and `treeEdges` threw — that is how the
  `edge.type` guard was found. The 100-node sample raced the panel's 3 s poll and is recorded as unreliable.
- **Evidence paging is `offset` on the existing endpoint**, with a test that pages a 13-row run in chunks and
  compares to the single-page result. No new UI: nothing in the product lists raw evidence rows yet.

## Round 22 — Release candidate audit

- **The planner's budget is a product decision, not a tuning knob.** `max_tokens=2400` made a real plan fail
  with `output_limit`; `timeout_seconds=60` made another fail at 122 s. The model needs room for a structured
  answer (~2 000 output tokens, 40–110 s). Settled at 6000 tokens / 120 s (the request contract's hard cap),
  plus an instruction to plan the shortest workflow (≤ 14 nodes), which brought a real plan to ~50 s.
- **One malformed reply gets exactly one correction.** Re-prompting with "Reply with the JSON object only"
  recovers the common prose-wrapped answer; a second failure is a 503 with a reason. An open retry loop would
  turn a flaky model into a slow, expensive endpoint. Both branches are pinned by tests on the provider's
  recorded requests.
- **A scalar where a declared list belongs is a shape correction, not a claim.** `_inputs` wraps a non-empty
  scalar into a one-item list only when the catalogue declares that input as a list. It never invents a value
  and never guesses a node's meaning.
- **The pipeline fit depends on geometry primitives, not on the extent object.** The reviewer's P1: every 3 s
  live poll rebuilt `pipelineExtent`, re-ran the fit and pulled a panned user back to stage 1. Depending on
  `.right` / `.bottom` keeps the fit when the pipeline actually changes and leaves the viewport alone when it
  does not. The regression could not be reproduced in the browser (no node was ever live during the probe),
  so this one is verified by reading, and `r22.md` says so.
- **`traceExtent` measures a card by its real width.** Stacked cards are 300 px, columns are 236 px; using one
  constant over-estimated the zoom and clipped deep cards on a phone. `initialWidth` is carried by the node
  and is the only width the model trusts.
- **Two 500-classes stay out of the planner endpoint.** A non-list `nodes`/`edges` and a provider reply that is
  a bare string now produce `valid: false` (or a 503 with a reason) instead of an unhandled exception; the
  endpoint only translates `WorkflowPlanUnavailable`.
- **The release verdict is set in five separate levels.** CORE_PRODUCT / WORKFLOW_STUDIO / DAG_EXECUTION /
  MULTI_INSTANCE / RELEASE_CANDIDATE are reported independently, so a passing product path cannot silently
  upgrade an unverified execution or deployment claim.
