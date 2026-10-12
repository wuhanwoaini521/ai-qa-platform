# Requirement Selection Visibility

- run-date: 2026-10-12
- task-type: bug-fix (user-visible UI issue)
- scale: small

## Problem and Root Cause
The Workspace requirement stage hides the legacy `RequirementList` and leaves the context rail collapsed by default. The toolbar only exposes requirement actions; the selected requirement identity is otherwise visible in the detail card lower on the page, with no always-visible control for switching among project requirements. The user therefore has to expand the context rail or infer the active requirement from the detail content.

The data and selection callback already exist in `RequirementsPage` (`reqs.requirements`, `reqs.selectedReq`, `handleSelectRequirement`). The smallest safe fix is to surface that existing selection state in the Workspace requirement toolbar. A labeled identity plus an accessible native selector when there are multiple requirements keeps current selection semantics and calls the existing callback, which also updates shared Workspace context / URL state.

## Acceptance Criteria
1. With the context rail collapsed, the requirement stage identifies the selected requirement by display ID and title in the visible toolbar.
2. If the project has multiple requirements, a keyboard-accessible, labeled selector lists each requirement as ID + title; choosing one updates the displayed requirement and Workspace context.
3. With one requirement, show the same identity without a misleading inert switcher.
4. Existing Jira import, create, and AI-analysis controls remain available and the layout adapts without document-level horizontal overflow at desktop, tablet, and mobile widths.
5. English and Simplified Chinese labels are present; light and dark theme colors use existing design tokens.

## Risk and Scope
- Risk: low, isolated React presentation and selection wiring; no API/model changes.
- Out of scope: changing default selection policy, context-rail persistence, requirement creation flow, generated IDs, or persisted user data.
- Initial browser inspection: local Workspace at 1280×633, context rail collapsed, one Golden Demo Shop requirement. The detail card shows the title, but the toolbar only contains Jira / create / analysis actions. The screen has no document overflow before change.
