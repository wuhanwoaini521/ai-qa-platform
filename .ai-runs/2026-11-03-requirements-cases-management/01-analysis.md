# 分析

## Current repository/code state

Initial branch is `feat/project-requirements-navigation` at `941823433d57a745aaacf6e73fccdffb085fb5d0`. Preserve the prior uncommitted navigation changes in `apps/web/src/components/Navigation.tsx`, `apps/web/src/app/workspaceContext.ts`, `apps/web/src/pages/ProjectsPage.tsx`, `apps/web/src/features/lifecycle/ProjectOverviewPage.tsx`, English/Chinese navigation locales, and `docs/agent-handoff.md`. Do not alter unrelated untracked runtime or run artifacts.

## Existing capabilities

`apps/web/src/features/management/ProjectManagementPage.tsx` already fetches project requirements and test cases and provides three URL-backed tabs, search/status/priority/relationship filters, four summary cards, expandable traceability rows, and a case relation selector. The unlinked-requirement and independent-case cards already target filtered results. `apps/web/src/features/management/managementModel.ts` contains filtering, counts, display IDs, and test-design relation locks.

Existing persisted relation is one nullable `TestCase.requirement_id`; no many-to-many. `Requirement` stores `description`, text `acceptance_criteria`, `status`, `external_system/id/url`, `qa_model`, timestamps. `qa_model.criteria` stores structured acceptance points; the lifecycle panel already saves text and criteria together while retaining IDs. No requirement priority, owner, module, or typed Discovery-run source field exists. No schema migration is indicated.

Existing `/api/requirements` and `/api/test-cases` create/update APIs enforce project and lifecycle validation. Reuse `RequirementFormModal`, `TestCaseFormModal` / `useTestCaseFormModal(projectId, requirementId)`, and `api.updateTestCase`. A case tied to a test design is locked against reassociation. Discovery draft lineage is present in run result/narrative only; do not infer a source badge from title or free text. Run history lacks a direct case ID in the current repository response; exact unique binding `nodeid` plus project/run/execution matching is required before showing a result.

## Confirmed gaps

- Generic first-cell min width is 260px; trace expand control is 32px; ID/name allocation is not explicit.
- Requirements tab has no details drawer or direct create/link actions; case create from a requirement is not available in this hub.
- Active filters and result counts are not consistently visible; failed relation save reverts the user's selected value.
- Page/title and filter labels include generic/ambiguous “状态” and “需求与测试用例”.
- Tab ArrowLeft currently follows the same forward behavior as ArrowRight.
- No migration/API changes are needed unless later source inspection finds a real missing persisted field.

## Verification constraints

Existing local development services occupy ports 8000 and 5173 and must stay read-only. Browser verification will use Playwright 1.62.0 with Chromium from the installed Python environment and a separate API/Vite instance backed by a disposable SQLite database and temporary workspace/artifact directories. No QA runtime runs will be started. Use a synthetic project and fixtures only.

## Risks

- No local existing-authenticated browser session is available. The previous default login failed against the normal local database; do not retry there.
- Current uncommitted navigation work must remain intact.
- Do not label relation counts as acceptance coverage or automation; do not infer execution; no source/ownership/priority/module values unless typed and persisted.
