# Workflow

This reference expands the control flow in `SKILL.md`. Keep the process proportional to the requested change; a delivery workflow does not authorize unrelated work.

## Repository Understanding Gate

Before editing code or creating implementation files:

1. Read applicable `AGENTS.md` and repository guidance (`CONTRIBUTING.md`, `README`, local instructions).
2. Map the project structure and identify the relevant package/module boundaries.
3. Locate and read the existing implementation and its callers.
4. Find the related tests and test helpers.
5. Read the relevant configuration and discover actual run, test, lint, typecheck, and build commands.
6. Understand the architecture and data/control flow around the change.
7. Assess behavior, architecture, data/security, user-facing, and regression impact.
8. Reuse an existing implementation or extension point when one already fits.
9. Only then plan the change. Do not create a new file before checking for an existing home.

Record concise evidence and affected areas in `01-analysis.md` for an authorized delivery run. A read-only request is not a delivery run and produces no repository artifact.

## Delivery stages

1. **Classify and assess risk.** Choose one primary type and a `LOW`, `MEDIUM`, or `HIGH` risk using `task-routing.md`; keep additional applicable gates.
2. **Analyze requirements and impact.** Define the user outcome, constraints, compatibility, affected callers/data, unknowns, and verifiable acceptance criteria. See `requirements-analysis.md`.
3. **Plan.** List coherent changes, expected files, verification, review, regression scope, and acceptance checks. Revise the plan if evidence changes the approach; record the reason.
4. **Implement.** Follow `development.md`; solve the demonstrated cause and keep the change scoped.
5. **Verify behavior.** Run the most relevant targeted checks first, then relevant integration and functional checks. Exercise the actual command, API, script, or UI when possible.
6. **Review independently.** Run code review for every delivery. Add UI review for user-facing UI changes. Fix blocking findings and repeat affected checks and reviews.
7. **Regress.** Select coverage from the risk and impact surface; HIGH-risk work should use broader regression.
8. **Accept and report.** Compare evidence against each criterion and use only `PASS`, `PARTIAL`, or `FAIL` as defined in `final-acceptance.md`.

## Run log boundary

Creating `.ai-runs/` is a repository write. For an authorized modification request, initialize its log only after confirming that the task is a real delivery workflow and classifying its scope. Use `scripts/init_run_log.py` to avoid overwriting an earlier run. Fill result sections only after actions occur. Never create a log, plan file, or placeholder results for read-only work.

## Failure and scope changes

Use the loop `failure → evidence/root cause → source fix → rerun affected checks → regression`. Do not change acceptance criteria to make a failure disappear. If new evidence changes scope, update `02-plan.md`, record the change, and preserve completed work. Ask the user only for a real decision or authorization that cannot be inferred safely.

## Large or broad changes

For cross-module, migration-like, or broad UI changes, split work into milestones in `02-plan.md`. For a broad UI redesign, validate one representative page before extending the direction. Do not add a ceremony or milestone to a narrow task without a concrete benefit.
