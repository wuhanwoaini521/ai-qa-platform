# Flow canvas — P0 read-only (2026-11-01)

Entry: `/flows?projectId=<id>&requirementId=<id>[&scenarioId=]`; also linked from the requirement
「场景设计」tab ("在画板中查看").

## What it does

Expands a requirement scenario into four columns on one canvas, from real data only:

`验收标准（coverage.criterion_ids） → 场景 → 动作（actions[]） → 期望（expected_outcomes[]）`

- Pure layout function `buildScenarioFlow` (no React), covered by 4 node tests.
- Read-only: no writes, no execution, no new API.
- Fit-to-width scaling so the last column is never clipped at 1280/1440.
- Scenario switcher writes `scenarioId` through the router (no history hacks).

## Files

- `apps/web/src/features/flow-canvas/flowGraph.ts` — layout + edge routing
- `apps/web/src/features/flow-canvas/FlowCanvas.tsx` — SVG connectors + node cards
- `apps/web/src/pages/FlowCanvasPage.tsx` — data loading, scenario switch, empty/error states
- `apps/web/src/app/routes.tsx` — `/flows` route
- `apps/web/src/i18n/locales/{zh-CN,en}/flowCanvas.json` — 27th namespace

## Verified

`tsc`, ESLint, frontend tests **238 passed** (4 new), `vite build`, i18n 3,558 keys.
Screenshots: `evidence/flow-canvas-1440x900.png`, `evidence/flow-canvas-1280x800.png` (8 nodes, no
horizontal page overflow).

## Next (P1, not built)

Editable canvas: node palette + drag/connect, `flow_to_steps()` compiling to the existing
`RecorderStep[]` → `generate_python_case`, preview diff, human save, then the existing run/evidence
path. No new execution engine.

---

# P1 editable editor + P2 branches/variables (same day)

## Editor

`/flows/edit?projectId=…&requirementId=…[&scenarioId=…]` (linked from the read-only canvas and the
requirement design tab).

- Tree editor: node palette (navigate/click/fill/assert_text/assert_visible/wait/condition), drag or
  up/down to reorder, inline inspector per node kind, delete.
- Condition nodes own two branches (`条件成立` / `条件不成立`) with their own step lists.
- Client validation mirrors the server contract and blocks compile with readable messages.
- Compile happens through `POST /api/flows/compile` (debounced) → code preview + node/step counts.
- Save writes `tests/<test_name>.py` via the existing workspace file API; Run creates the normal
  `TestRun` for `tests/<name>.py::<name>` and navigates to the run page.
- Deviation: connections are structural (tree order/branches), not free-form wiring. Free-form
  edges cannot express branches without an execution engine; the tree keeps every flow compilable.

## P2: branches and data variables

- `RecorderStep` gained optional `condition_kind` / `condition_value` / `then_steps` / `else_steps`;
  `generate_python_case` now renders them recursively (`if …count() > 0: … else: …`) with the existing
  evidence markers, so compiled branches stay on the verified generation path.
- Fill nodes can read a run environment variable (`QA_DATA_*`) instead of a literal, reusing the
  existing `value_redacted` + `secret_env_var` generation.
- `apps/api/app/services/flow_compiler.py` validates the authored document (start node, duplicates,
  depth ≤ 5, per-kind requirements) and compiles it through the recorder generator.
- `POST /api/flows/compile` returns `{code, test_name, node_count, step_count, warnings}`. Read-only:
  nothing is written or executed by this endpoint.

## Verification (real runs)

| Check | Result |
|---|---|
| Compiler tests | **14 passed** (`apps/api/tests/test_flow_compiler.py`) |
| Recorder regression | **74 passed** (save flow, service, variables, websocket) |
| Frontend | **244 passed** (6 new editor-model tests), tsc, ESLint, i18n 3,620 keys |
| Lint | Ruff check + format clean |
| Editor screenshot | 6 nodes from the real scenario, code preview 2,418 chars, 1440 & 1280 |
| Branch run (true) | `test_flow_offer_true` → **PASSED** (page with `#offer` → accept) |
| Branch run (false) | `test_flow_offer_false` → **PASSED** (page without `#offer` → dismiss) |

Evidence: `evidence/flow-editor-1440x900.png`, `flow-editor-1280x800.png`,
`flow-compile-runs.json` (both compiled sources and run results).

## Notes / limits

- Recorded URLs are redacted by `SensitiveRedactor` (query strings are dropped), so fixture pages
  must be addressable by path; compiled flows inherit this security behaviour by design.
- The tree editor has no explicit "connect" interaction; reorder + branches cover the flows this
  product can execute today.

---

# P3: assertion → criterion → case traceability (same day)

## What was added

- Assert nodes carry `criterion_ids` (checkbox list from the requirement's real criteria).
- Validation warns (does not block) when an assertion node has no criterion: `warnCriterionMissing`.
- `POST /api/flows/compile` now returns `assertions[]` (`node_id`, `criterion_ids`, `statement`, `check`).
- **Human-triggered bind** on save: `POST /api/flows/bind-case` writes/updates a test case whose
  `test_model.assertions` are `CaseAssertion` rows carrying `criterion_id`, `statement`, `check` and the
  flow's `nodeid`, then binds the nodeid to the workspace file. The requirement's script map is left
  untouched: it is owned by the generated-from-assertions path and requires requirement assertions.
- The existing case assertion panel therefore shows run state per criterion without any new table.

## Live evidence (real UI + real run)

`evidence/flow-bind-evidence.json`, `evidence/flow-editor-bound-1440x900.png`:

| Step | Result |
|---|---|
| Editor seeds SCN-004, fill locators, bind AC-001 / AC-002 to the two assertion nodes | save |
| Save → `POST /api/flows/bind-case` | case `tc_flow_3ce338440e498ec2d5ba63284bf10` created |
| Run `tests/test_scn_004.py::test_scn_004` | **PASSED** |
| `GET /api/test-cases/{case}/assertions` | `AC-001 → PASSED`, `AC-002 → PASSED`, nodeid `tests/test_scn_004.py::test_scn_004` |

## Tests

- `apps/api/tests/test_flow_binding.py`: bind creates case assertions with nodeid; re-bind is idempotent;
  unknown criterion → 422; cross-project requirement → 422.
- Frontend: `toggleCriterion` + warning lifecycle (7 editor-model tests); 245 frontend tests total.
- Backend regression: 77 passed (flow binding + compiler + recorder save/service/variables/websocket).

## Limits

- Binding happens on save and only when at least one assertion has a criterion; otherwise the save
  still writes the file and the editor says so.
- Case identity is deterministic (`tc_flow_<hash>`), so re-saving refreshes the same case.
