# Implementation

- `apps/web/src/features/workspace/WorkspacePage.tsx`: initialize automation-stage visits with the context panel closed and close it when entering automation; the existing header toggle can reopen it.
- `apps/web/src/features/automation-studio/AutomationStudioPage.tsx`: collapse the embedded file explorer on phone widths, restore it above 600px, and preserve the existing manual toggle.
- `apps/web/src/features/workspace/workspace.css`: cap the explorer width when opened on a phone.
- `apps/web/src/components/AIExecutionTimeline.tsx` and new `aiExecutionTimelineModel.ts`: only show the provider-unavailable badge for structured provider failure reasons.
- `apps/api/app/services/operation_trace.py`: generic operation failures no longer advise checking provider health without evidence.
- Added `apps/web/tests/ai-execution-timeline-model.test.mjs` for provider outage and non-provider failure classification; strengthened `apps/api/tests/test_runtime_operation_stream.py` to assert provider-neutral errors and redaction.
- Preserved pre-existing edits in the workspace files; no API, lockfile, or dependency-definition changes.
