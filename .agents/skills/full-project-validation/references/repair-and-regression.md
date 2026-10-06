# Audit + Repair and Regression

## Repair Authorization

Audit Mode is read-only for product files. Do not modify application source, tests, configuration, or behavior merely because a check fails. Test-run temporary output permitted by the repository is not repair authorization.

Enter Audit + Repair only on an explicit request such as “check and fix”, “fix anything you find”, or “test it and repair failures”. Scope each code change to a verified issue. Reuse existing project structure and avoid unrelated cleanup or whole-project rewrites.

During an authorized system-wide repair campaign, full-project-validation remains responsible for the audit scope and overall health verdict, including when several defects need local fixes. Apply the repository's established engineering and review practices to each fix without restarting or duplicating the full delivery workflow. Use project-delivery for a separate, independently scoped change requested by the user.

## Safe Fixes

For every repair, establish evidence and a root cause before changing code. Never make a failure disappear by skipping or deleting a failing test, adding `xfail`, removing assertions, swallowing errors, silencing console output, adding unjustified timeouts/retries, disabling a feature, or mocking a broken real integration. Use such mechanisms only when evidence shows they are the intended design, and explain that evidence.

## Retest and Regression

After a repair:

1. Rerun the exact failing command or user flow.
2. Run its related unit/integration/contract tests.
3. Rerun the affected API, runtime, page, or Golden Journey path.
4. Expand to broader regression in proportion to impact and severity; prioritize broader checks for P0/P1 findings.

Record actual commands, results, and any unresolved findings. If the fix itself cannot be validated, report `PARTIAL` or `FAIL` according to the remaining impact. Do not turn an Audit task into a delivery project through opportunistic refactoring.
