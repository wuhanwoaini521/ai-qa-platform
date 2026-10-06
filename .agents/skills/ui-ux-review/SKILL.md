---
name: ui-ux-review
description: "Review or improve an existing product's UI/UX, information architecture, and workflows when interfaces are confusing, cluttered, repetitive, or hard to use. Use for usability audits, workflow simplification, page consolidation, and UX-led redesign. Exclude non-UX feature, backend, or maintenance work, implementing approved designs without UX review, system-wide health checks, technical explanations, architecture-only questions, and framework comparisons; use project-delivery for scoped implementation and full-project-validation for whole-app health."
---

# UI/UX Review

Review whether an existing product is understandable, coherent, and usable across its real user journeys. When the user explicitly asks for changes, improve the experience with the smallest coherent implementation; do not treat a review request as permission to edit.

## Modes

- **Review Mode (default):** observe, analyze, preserve evidence, and recommend. Do not edit source, styles, components, routes, tests, configuration, or create design implementation files.
- **Improve Mode:** enter when the user explicitly asks to redesign, fix, simplify, or implement UX improvements. Establish the UX goal and acceptance criteria, then implement and verify the scoped changes.

## Workflow

1. Understand the product, primary user, task, navigation, existing patterns, and recent changes before judging the UI. Read `references/product-and-journey.md`.
2. Identify the Golden Journey and map relevant pages and workflow transitions. Review information ownership, repeated functionality, and whether related tasks remain in context; read `references/information-architecture.md`.
3. Inspect relevant visual hierarchy, interactions, component consistency, feedback, and UI states. Reuse the existing design system. Read `references/visual-and-interaction-review.md`.
4. When the product can run and browser capability exists, inspect the real UI and interactions. Separate visual evidence from interaction evidence; read `references/browser-verification.md`.
5. In Review Mode, report evidence, user impact, priority, and recommendations without changes. In Improve Mode, make the smallest coherent change, verify the live browser flow and responsive behavior when the product can run and browser capability exists, and run relevant regression checks. If browser verification is unavailable, record the limitation and reflect it in the verdict.
6. Use `references/reporting-and-priorities.md` for the appropriate report structure and verdict.

## Review Gates

- Prioritize workflow continuity and user goals over isolated visual polish. Do not infer that adding pages, cards, or decoration improves usability.
- Actively inspect discoverability, duplicated or redundant actions, page proliferation, loading/empty/error/success/disabled states, system feedback, and basic accessibility.
- If a UI exists but cannot be opened, state what evidence was available and what interaction evidence remains unverified. Source inspection or screenshots alone do not prove a workflow works.
- Do not claim formal WCAG conformance from this review; report observed accessibility issues and the limits of the check.

## Boundaries and Composition

- Use this skill for UX-led review and changes where usability, workflow, navigation, information architecture, or visual interaction quality is the main goal.
- Use `project-delivery` for a scoped feature, backend fix, refactor, or implementation of an already approved design. For UX-led implementation, this skill owns experience analysis and acceptance criteria; when available, compose with `project-delivery` for engineering delivery gates. If unavailable, follow the repository's normal verification practices without requiring another skill.
- Use `full-project-validation` for system-wide product health, all-feature testing, and broad regression. If that skill is unavailable, report broad health validation as unverified; a UI review does not establish whole-application health.
- For mixed requests, keep the UX assessment and overall health validation distinct, and report which evidence supports each conclusion.

## References

- `references/product-and-journey.md` — product understanding, workflow-first review, Golden Journey, and scope.
- `references/information-architecture.md` — page responsibilities, navigation, duplicate functions, consolidation, and progressive disclosure.
- `references/visual-and-interaction-review.md` — hierarchy, layout, consistency, states, feedback, and visual restraint.
- `references/browser-verification.md` — live browser, screenshot-only evidence, responsive checks, and accessibility review.
- `references/reporting-and-priorities.md` — severity, evidence-based findings, review and improve report formats, and verdicts.
