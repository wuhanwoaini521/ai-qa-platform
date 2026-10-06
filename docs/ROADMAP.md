# AI QA Platform — Engineering Roadmap

This document outlines future milestones and strategic enhancements for the platform.

---

## 0. Platform Safety Invariants (non-negotiable)

Every item below — shipped or planned — must respect these invariants. A roadmap item that violates them is a bug in the roadmap.

1. **AI never decides PASS / FAIL.** Test verdicts come from real test execution exit codes only. AI may summarize, classify, and explain; it may never override a verdict or declare a failing test passing.
2. **AI never mutates code without explicit human approval.** Repair flows end in a *proposal* + *diff*; a human applies it. There is no confidence threshold high enough to skip review.
3. **Determinism over autonomy.** Test selection, gating and coverage are computed from recorded execution data, not from model judgement. Model output is advisory metadata.
4. **Preview before external mutation.** Jira, TestRail, GitHub and Jenkins writes are preview-first and require explicit confirmation flags.
5. **No unattended agent loops** against customer systems. Automation is bounded, reviewable and reversible.

---

## 1. Near-Term Milestones (v1.1 - v1.2)

- [ ] **Visual Regression with explicit review**: computer-vision diffing for Playwright screenshot comparisons, with deterministic region masking (ignore timestamps, dynamic banners) and a human-approved baseline update step.
- [ ] **Assisted Locator Repair — batch review**: improve the existing proposal-only workflow with bulk review of repair candidates, side-by-side diffs, and a one-click human-approved patch that opens a normal pull request. *No auto-apply.*
- [ ] **Multi-Tenant Organization Support**: organization isolation with per-organization data partitioning, custom domains, and SAML 2.0 / Okta SSO.
- [ ] **Deterministic Regression Selection**: expand change-impact analysis so regression scope is derived from recorded executions, bindings and git changed files — never from model judgement.

---

## 2. Mid-Term Milestones (v1.3 - v2.0)

- [ ] **AI Test Case Drafting from Figma & Storybook**: ingest design tokens and UI mockups to produce *draft* Gherkin scenarios and Playwright skeletons that a human adopts through the existing preview/adopt flow.
- [ ] **Multi-Region Runner Mesh**: geo-distributed worker clusters with latency-aware scheduling of already-defined jobs (scheduling only; verdicts stay deterministic).
- [ ] **AI-assisted Regression Recommendation**: rank existing tests by predicted relevance to a change and surface the ranking as a *recommendation* with its evidence, leaving the executed scope under human control.
- [ ] **Flaky Root-Cause Mining**: statistical analysis over execution history to attribute flakiness to environment, timing, or locator instability, feeding the existing proposal-only repair pipeline.

---

## 3. Platform Versioning History

- **v0.1.0** — Phases 1-3: Core Foundation & Automation Studio V2
- **v0.2.0** — Phases 4-7: Real Execution, Flaky Intelligence & Jenkins
- **v0.3.0** — Phases 8-10: GitHub, Jira, TestRail, Coverage & Release Gate
- **v1.0.0** — Phases 11-13: Enterprise RBAC, Distributed Runner Grid, Production Docker & Prometheus Observability
- **v1.0.0-rc.1** — Phase 13.5/14: architecture stabilization and real-project pilot hardening
