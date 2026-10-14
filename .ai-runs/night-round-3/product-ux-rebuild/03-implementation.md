# Implementation record

## Product changes

- Passed `WorkspaceRunConfig` from the workspace into embedded Automation Studio's existing run hook. A normal Studio run now sends the same environment, region, browser, and worker count as the Run Controls dock; retries still reuse the historical run's configuration.
- Kept the existing target order (explicit Test Explorer node → selected case binding → active file) and made the play button say **Run Case / Run File** accordingly. The active file/case mismatch is no longer hidden behind the vague “Run Test” label.
- Removed the duplicate project dropdown only from embedded Studio. The app shell remains the project switcher, and Quick Open stays as a labeled, accessible action. Standalone Studio behavior is preserved.
- Made the five-step workspace rail fit tablet widths and switch to a compact, non-scrolling five-step rail at 360px; full step/status labels remain in each button's accessible name.
- Restored padding to labeled Studio toolbar actions (they had been included in an icon-only zero-padding reset). The paused-debug toolbar now has 44px-minimum button widths with no intersections at 1440px.
- Rendered missing/invalid browser-event timestamps as `—` instead of the literal `Invalid Date`.

## Files in scope

`AutomationStudioPage.tsx`, `ProjectSelector.tsx`, `useRunExecution.ts`, `WorkspacePage.tsx`, `workspace.css`, `index.css`, `browserModel.ts`, `RuntimeBrowser.tsx`, `studioShell.json` (English and Chinese), `runtime-browser.test.mjs`, plus the already-dirty but directly related run-target implementation and test (`runTarget.ts`, `automation-studio-run-target.test.mjs`). No API/backend, source-write, repair-approval, or data model changes.

## Interaction rationale

One ordinary run can still be launched contextually from the editor or the shared dock; both now dispatch the same configured case/file target. Results and live browser details already exist in the workspace, so the flow was connected rather than duplicated into another page/runtime. AI Repair remains an inspectable proposal/approval flow and was not invoked in this pass.
