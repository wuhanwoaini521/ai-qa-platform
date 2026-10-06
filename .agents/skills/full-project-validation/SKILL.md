---
name: full-project-validation
description: "Run a system-wide project health check when asked to test the whole application, verify major features, run a full regression, or find what is broken. Assess repository checks, automated suites, runtime, APIs, browser flows, and the project's critical user journey; repair confirmed issues only when explicitly requested. Exclude a single feature or bug fix, a one-page redesign, scoped refactoring, code or error explanations, architecture explanations or advice, technical Q&A, and library comparisons; use project-delivery for scoped changes."
---

# Full Project Validation

Validate whether an existing software project is healthy across its actual checks and critical user journeys. This skill owns system-wide discovery and verification; `project-delivery` owns a scoped implementation, bug fix, refactor, or UI change.

## Modes

- **Audit Mode (default):** inspect, run checks, reproduce failures, and report. Never change application source, tests, configuration, or product behavior. Test-generated temporary output is allowed when consistent with repository rules.
- **Audit + Repair Mode:** enter only when the user explicitly asks to fix findings. Keep each fix tied to evidence and a root cause; then retest and regress. A request to find, test, or explain failures alone is not repair authorization.

## Workflow

1. Pass the Project Discovery Gate: read repository guidance, README, layout, actual manifests, runtime and package-manager requirements, test/build scripts, CI, service boundaries, and available API/browser tooling. Read only files that exist; do not assume a stack.
2. Build a scope and validation matrix before running checks. Use `references/validation-levels.md`; mark checks `NOT APPLICABLE` only when the project has no such capability and `NOT AVAILABLE` when a relevant capability exists but cannot be used here.
3. Run applicable validation from repository/static checks through automated tests and runtime, then API/service and browser verification as relevant. Identify, execute, and report the project's Golden Journey; see `references/browser-and-golden-journey.md`.
4. For failures, preserve evidence, classify product failure versus environment blocker, reproduce where possible, and establish a root cause or clearly labeled probable root cause. Read `references/issue-investigation.md`.
5. In Audit + Repair only, make the smallest fix supported by evidence. Retest the exact failure, related tests, and impacted journey before selecting broader regression. Read `references/repair-and-regression.md`.
6. Report verified scope, counts, runtime/browser outcomes, coverage and unverified areas using `references/final-report.md`. Final health is exactly `PASS`, `PARTIAL`, or `FAIL`.

## Validation Gates

- A full test suite passing is evidence, not proof that every user workflow works. Combine automated checks with runtime, API, browser, and Golden Journey evidence where applicable.
- Do not claim full coverage without an executed page/feature matrix. Prioritize core flows and show what was tested and what was not.
- A critical required check blocked by the environment cannot be silently skipped or treated as passing. UI-heavy projects need real browser evidence when available; if unavailable, say `Browser verification: NOT AVAILABLE`.
- Never hide product failures to make a project look healthy. In Audit Mode, findings end in a report without product changes.

## References

- `references/validation-levels.md` — discovery, validation matrix, and static/test/runtime/API levels.
- `references/browser-and-golden-journey.md` — page/feature coverage and browser-backed critical paths.
- `references/issue-investigation.md` — failure categories, severity, evidence, and environment distinction.
- `references/repair-and-regression.md` — explicit repair authorization and safe retest/regression.
- `references/final-report.md` — required report sections and verdict criteria.
