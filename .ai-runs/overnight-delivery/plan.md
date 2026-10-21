# Overnight delivery mission — plan and state

Started: Round 17 (versioned QA workflow studio) → Round 22 (release candidate audit).
Repo: `/home/hans/self-github/ai-qa-platform`.

## Starting facts (verified, not assumed)

- HEAD at start: `c6d08df` (the mission brief said `b3c1b28`; that is one commit behind — recorded in
  `decisions.md`).
- Working tree at start: Round 17 backend work uncommitted (contract, migration, repository, service,
  HTTP endpoints, tests), plus the usual untracked `.ai-runs/**` and `runtime/backups/**`.
- Unpushed commits at start: `23`.
- Baseline gates inherited from Round 16.5: backend `960 passed, 11 skipped`; frontend `213 passed`;
  real Chromium `13/13`. These are re-verified on the final code, never assumed.

## Round order

| Round | Theme | Time budget | Status |
|---|---|---|---|
| 17 | Versioned QA Workflow Studio | 3h | RUNNING |
| 18 | Runtime reliability (multi-instance) | 3h | PENDING |
| 19 | AI workflow planner | 3h | PENDING |
| 20 | CI / PostgreSQL / deployment | 3h | PENDING |
| 21 | UX / performance / observability | 2h | PENDING |
| 22 | Release candidate audit | 3h | PENDING |

## Per-round protocol

AUDIT → DESIGN → IMPLEMENT → TEST → REVIEW → ACCEPTANCE → COMMIT → HANDOFF.
A blocked stage is recorded in `blockers.md` with evidence, marked BLOCKED, and never reported as PASS.

## Round 17 slices

1. **Contract + storage** (done before the mission started, committed as slice 1): graph spec,
   node catalogue, validation rules, tables + reversible migration `0019_workflow_definitions`.
2. **Service + HTTP** (slice 1): draft save with stale-editor guard, publish, restore, compare,
   compile-to-plan, project ACL + role split (engineer drafts, lead publishes).
3. **Editor** (slice 2): React Flow editing mode in the existing canvas — add/remove nodes from the
   whitelist, connect/disconnect, edit inputs, undo/redo, auto-layout, validation panel, version
   list, version compare, publish button gated by permission.
4. **Definition vs execution diff** (slice 3): compare a published version with a real task's trace.
5. **Evidence + test-data governance** (slice 4): task-level evidence refs for new executions,
   acceptance-data isolation (`e2e-acceptance` tag), coverage numbers excluding fixtures.
6. **Acceptance** (slice 5): real Chromium pass over create/edit/save/version/publish/permissions/
   refresh/diff, plus A/B/C verdicts.

## Evidence layout

- `rounds/round-17.md` … `rounds/round-22.md` — per-round audit, evidence, numbers.
- `screenshots/` — real browser captures (before/after, viewports).
- `regression/` — gate output.
- `final-report.md` — the delivery contract answer.
