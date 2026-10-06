# Findings, Reports, and Priorities

## Prioritize Findings

- **P0:** core UI is unusable or blocks access to the product.
- **P1:** the Golden Journey or a high-impact primary task is materially blocked.
- **P2:** substantial friction, confusing structure, redundant functionality, or a clear contained layout problem.
- **P3:** low-impact consistency or visual polish issue.

Each important finding should state:

```text
Finding:
Evidence:
User impact:
Recommendation:
Priority:
```

Anchor claims to a page, interaction, route, viewport, observed state, or reproducible task. Separate observed evidence from interpretation. Avoid generic advice such as “make it cleaner” without explaining what users struggle to do.

## Review Mode Report

Use this structure and mark areas outside the requested scope as not reviewed:

```markdown
## UX Summary
## Product / User Goal
## Golden Journey
## Information Architecture
## Workflow Friction
## Duplicate / Redundant Functions
## Discoverability
## Visual Hierarchy
## Layout / Responsive
## States & Feedback
## Accessibility
## Issues
## Priority Plan (Now / Next / Later)
## Unverified Areas
## Final Assessment (HEALTHY / NEEDS IMPROVEMENT / POOR)
```

## Improve Mode Report

Summarize the UX goal, problems found, changes made, affected files/components, browser and responsive verification, accessibility review, regression results, and remaining issues. Include a concrete **Before / After** workflow comparison; describe the user outcome rather than claiming the UI is merely “more modern.”

Use **PASS / PARTIAL / FAIL** for implementation acceptance. `PASS` requires the in-scope interaction and main workflow to work with relevant verification complete. If a required regression check cannot run, record the blocker and do not claim `PASS`. Use `PARTIAL` when material browser, responsive, accessibility, or regression evidence is unavailable or important issues remain. Use `FAIL` when a P0/P1 in-scope issue remains or the changed flow is broken. These delivery verdicts are separate from the Review Mode UX assessment.
