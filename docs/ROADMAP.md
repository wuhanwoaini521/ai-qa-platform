# AI QA Platform — Engineering Roadmap

This document outlines future milestones and strategic enhancements following the successful completion of Phase 1 through Phase 13.

---

## 1. Near-Term Milestones (v1.1 - v1.2)

- [ ] **Visual Regression & Canvas AI**: Computer vision diffing for Playwright screenshot comparisons with AI semantic region masking (ignore timestamps, dynamic banners).
- [ ] **Self-Healing Locator Auto-Apply Mode**: Optional policy-controlled auto-apply for locator repairs with 99%+ confidence threshold and auto-created git PR.
- [ ] **Multi-Tenant Organization Support**: Enterprise multi-tenancy with organization isolation, custom domains, and SAML 2.0 / Okta SSO integration.

---

## 2. Mid-Term Milestones (v1.3 - v2.0)

- [ ] **AI Test Case Auto-Generation from Figma & Storybook**: Direct ingestion of design tokens and UI mockups into Gherkin BDD scenarios and Playwright test skeletons.
- [ ] **Multi-Region Runner Mesh**: Geo-distributed worker clusters across US, EU, and APAC with latency-optimized runner scheduling.
- [ ] **Autonomous Regression Oracle**: Deep reinforcement learning agent simulating human exploratory testing to discover unexpected UI layout anomalies and state crashes.

---

## 3. Platform Versioning History

- **v0.1.0** — Phases 1-3: Core Foundation & Automation Studio V2
- **v0.2.0** — Phases 4-7: Real Execution, Flaky Intelligence & Jenkins
- **v0.3.0** — Phases 8-10: GitHub, Jira, TestRail, Coverage & Release Gate
- **v1.0.0** — Phases 11-13: Enterprise RBAC, Distributed Runner Grid, Production Docker & Prometheus Observability
