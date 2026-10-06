# Final Project Health Report

Use this report structure. Keep sections even when a layer is not applicable; state `NOT APPLICABLE` or `NOT AVAILABLE` with a reason rather than implying it passed.

```markdown
## Project Health
<PASS / PARTIAL / FAIL and one-sentence summary>

## Scope
<Requested scope, project areas and validation matrix summary>

## Environment
<Runtime, package manager, services, browser/tools and blockers>

## Static Checks
<Actual commands and results>

## Automated Tests
<Suites executed, counts, failures/skips and unrun suites>

## Runtime Health
<Startup commands, readiness, service/dependency results>

## API / Service Verification
<Success/error flows, or NOT APPLICABLE / NOT AVAILABLE>

## Browser Verification
<Routes/interactions and evidence, or required status>

## Golden Journey
<Selected end-to-end path and observed outcome>

## Coverage Matrix
<Pages/features by priority, tested result and unverified items>

## Issues Found
<Severity | Category | Evidence | Status>

## Root Causes
<Evidence-backed causes; mark uncertain conclusions Probable root cause>

## Fixes Applied
<Audit + Repair only; otherwise state no product changes were made>

## Regression Result
<Exact retest, related checks and broader regression result>

## Unverified Areas
<Specific checks, pages, flows, or dependencies not exercised and why>

## Remaining Risks
<Only evidenced, material risks>

## Final Verdict
<PASS / PARTIAL / FAIL>
```

## Verdict Criteria

- **PASS:** planned critical checks completed; no unresolved P0/P1 product failures; required suites passed; runtime, Golden Journey, and browser evidence passed where applicable. Do not grant PASS when a critical required check was blocked or silently omitted.
- **PARTIAL:** core evidence is positive but an important check is unavailable/blocked, only part of requested coverage ran, or only non-blocking P2/P3 issues remain. Name the limitation.
- **FAIL:** a P0/P1 remains, the app cannot start, the Golden Journey fails, a required suite has an unresolved product failure, or a significant regression remains.

Tests passing does not prove every feature is healthy. State counts and actual coverage (for example, “12/15 requested pages tested”), not “all features verified” unless the requested matrix was executed.
