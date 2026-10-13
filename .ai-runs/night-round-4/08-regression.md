# Regression — night round 4

## Risk and coverage

**Risk: HIGH.** The change crosses the API contract, persistence-backed state machine, UI workflow, and source-Apply boundary.

| Area | Checks | Result |
|---|---|---|
| State machine / persisted workflow | `test_failure_workflow.py`, `test_locator_repair_state_machine.py` | Included in 99 passed |
| Repair eligibility and exact Apply/verification | `test_locator_repair_eligibility.py`, existing explicit-approval tests in workflow suite | Included in 99 passed |
| API/OpenAPI/architecture | `test_openapi_contract.py`, `test_architecture_boundaries.py`, exporter `--check` | Passed |
| Web callers | typecheck, 146 tests, lint, production build | Passed |
| Actual user journey | Browser reject → persisted reload → Apply denied/source unchanged | Passed in isolated local service |
| Responsive/a11y | 1440/768/360 widths; scoped axe at 360 | No overflow; 0 scoped violations |
| Real AI + Jev | gated acceptance test | 2 skipped (not enabled; prior acceptance carried forward) |
| PostgreSQL / OS matrix | not available | Carried to final report; SQLite only in this round |
| Independent review | Orca invocation | BLOCKED by Orca.app path detection |

## Disposition

No round-4 regression was observed. Full repository regression is intentionally reserved for round 5. PostgreSQL concurrency and the independent-review gate remain open; neither is silently marked passed.
