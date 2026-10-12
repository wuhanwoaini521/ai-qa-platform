# Analysis

## Existing responsibilities in `apps/api/app/services/quality_discovery_service.py`

- Run/gap orchestration: create/get/list, gap actions and idempotency, pause/resume/stop/schedule/finish.
- Exploration planner/executor and deterministic browser policy: requirement parsing, observed control candidates, domain/action filtering, locator verification, budget and browser execution.
- State graph and evidence persistence: state fingerprints, graph transitions, frontier, actions, events, evidence/artifacts, AI/Jev telemetry and priority advisory.
- Quality projection: journeys, requirement/evidence checks, coverage, gap derivation/enrichment and functional specification.
- Shared contracts/serialization: run modes/status, schemas, errors and DTO mapping.

`quality_discovery_service.py` has 4,684 lines in the worktree and contains prior uncommitted Jev scoring changes. The initial worktree is broadly dirty. Refactor must copy the current contents and keep old import surface/method behavior; do not restore from HEAD.

## Existing task/recorder path

- Discovery persists successfully executed actions, source/destination states and edges. The source state's observed controls allow reconstructing deterministic RecorderStep locators; only successful state-changing graph edges are eligible for replay.
- `RecorderGenerateRequest` / `generate_python_case` already create deterministic pytest source from `RecorderStep` without writing files.
- Existing `CREATE_TEST` Task Runtime consumes `inputs.recorded_steps`, validates generated source, produces an approval diff, waits for explicit user approval, then writes/runs/registers through existing steps. Omitting `inputs.url` skips browser inspect/decision/action, so the draft path need not make new browser calls.
- Existing `_validate_goal_generated_test` rejects constant-true assertions, skip/xfail and pass-only exception handlers, but `CREATE_TEST` validation does not currently invoke it. Discovery-generated tasks must opt into this same checker; if no evidence-grounded meaningful assertion can be supplied, reject the draft.
- `WorkspacePage` already opens runtime task details/approval; `QualityDiscoveryPanel` can navigate to that existing preview/adopt surface.
- The `task_browser_executor.py` deterministic safety gate is not part of the proposed feature path and must remain unchanged.

## Verification seams

- Refactor: existing public API and module import compatibility; existing Discovery/API/candidate-policy tests.
- Feature: authenticated Discovery journey-to-task endpoint; Task detail reaches `WAITING` with generated artifact and diff; rejection for incomplete/non-replayable journeys or assertion bypass; workspace remains unchanged before approval; explicit approval continues through the existing Task Runtime path.

## Baseline evidence

`uv run pytest apps/api/tests/test_quality_discovery.py apps/api/tests/test_agent_tasks.py apps/api/tests/test_recorder_service.py -q`: **129 passed**.

`python scripts/init_run_log.py --help` could not run because that script does not exist in this checkout. No `.ai-runs/` ignore rule was found; run logs remain untracked and are not staged.
