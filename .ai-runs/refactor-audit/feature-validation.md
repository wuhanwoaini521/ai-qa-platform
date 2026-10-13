# Feature and Workflow Validation

## Approval-gated repair

Regression test: `apps/api/tests/test_failure_workflow.py::test_automatic_failure_analysis_requires_human_approval_before_patch`.

The test verifies that an automatically triggered analysis can complete diagnosis and prepare a Jev-selected, Playwright-verified proposal while leaving the source unchanged, creating no verification run, and emitting no verification event with `test_rerun=true`. The same proposal can then be explicitly applied and precisely verified. A failed verification is rolled back and does not launch a second analysis. The complete SQLite backend suite passed with this test included.

## Isolated product workflow in the browser

Using a temporary project and workspace at 127.0.0.1 only:

1. Created a project, requirement, and manual case `D9BA4C` (“Verify checkout completion status”).
2. Discovered six sample tests and ran the sample cart tests; the UI reported `PASSED · 3/3 passed`.
3. Bound the case to `tests/test_checkout.py::test_checkout_completes_order` and marked the binding active.
4. Started a run from the workspace run controls. Run `run_6b81199f1d6c` completed **PASSED**; the execution event stream recorded the browser click on “Complete order” and the test finished in approximately 2.4 seconds.

This validates the workspace binding/run flow with isolated fake app configuration; it is not evidence of a real AI/Jev repair.

## Live provider distinction

A direct `DecisionService.choose()` smoke call returned Jev provider `jev`, `candidate_1`, confidence `1.0`, and `fallback_used=false`. The separate opt-in end-to-end repair acceptance did **not** pass: the analysis was still `RUNNING` at the test assertion. Do not treat the direct call or simulated regression as live workflow acceptance. See `docs/AI_JEV_ARCHITECTURE_AUDIT.md` and `test-results.md`.
