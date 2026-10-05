# AI QA Platform — Agent Experience Rebuild

## Outcome

Implemented the first rebuild pass around one user path: QA Workspace for requirement-to-result work, Automation Studio for code/browser/debug, Live Workflow for execution progress, and Library for history. Code-level checks pass for the covered changes. Product acceptance remains **PARTIAL** because the six live journeys and screenshot review could not run: Chromium process startup returns `spawn EPERM` in this environment.

The attached screenshots are user evidence of the current pain points, not acceptance evidence for this code change. No fresh product screenshots were captured.

## Before problems and confusion map

| User-visible problem | Likely cause in the current flow | Change made | Verification limit |
|---|---|---|---|
| Run details/browser appeared immediately after starting a test | Studio opened the run dialog as soon as it received a Run ID | Removed the automatic open; the Browser button opens it on demand. Run status remains in the Studio status areas. | Source/build checks only; browser interaction not run. |
| Browser/runtime view was cramped | Run view was a narrow side drawer | Reused the existing dialog and centered it at up to 1360×940, with viewport-aware sizing. | CSS and build checked; no fresh visual review. |
| Live event stream occupied little space when no TaskStep DAG existed | The empty Flow area and event list did not share the available height | Let the event stream and its viewport fill the remaining panel height in the no-step state. | Runtime model tests pass; browser layout not captured. |
| Failure analysis exposed a long, low-level path | Model progress and trace events were shown as separate rows and analysis could start merely by opening the Browser view | Coalesced model progress into the diagnosis stage and made analysis an explicit action in the existing Failure workflow. | Stream/API tests pass; the user journey was not browser-tested. |
| AI diagnosis felt slow and opaque | The UI waited without token progress; transient retries and large requests could extend the wait | Stream real provider progress, bound prompt evidence/output, disable network retries for this path, cap total diagnosis time at 45 seconds and provider inactivity at 20 seconds. Include cleanup in the same deadline. | No live-provider latency benchmark; limits do not guarantee a specific response time. |
| Context was lost when moving among Workspace, Workflow, and Studio | Routes did not consistently carry the same entity identifiers | Reuse a shared URL context contract for project, requirement, case, task, run, failure, file, line, and node. | Context/model tests and code review pass; full browser round trip remains unverified. |

## Agent mental model

- **QA Workspace:** choose a requirement and move through cases, automation, results, and failures with a recommended next action.
- **Automation Studio:** edit, run, inspect a browser, and debug. Browser/run details open only when requested; the run view uses a centered large dialog.
- **Live Workflow:** inspect the same persisted task/run snapshot, event stream, steps, and evidence.
- **Library:** search and revisit history.

This keeps the product vocabulary at the QA task level. Internal runtime, provider, event, and locator details remain available as advanced evidence. The live five-second first-use test was not performed, so this is the implemented model, not a proven usability result.

## Capability status

Statuses below describe what this pass verified, not a claim that the complete feature is production-accepted.

| Capability | Status | Evidence / gap |
|---|---|---|
| Requirement analysis and coverage/case stages | PARTIAL | Workspace stage and task progress reuse existing APIs; full requirement-to-run journey not completed. |
| Automation generation and execution | PARTIAL | Existing generation/run services remain in use; no full browser journey. |
| Failure classification and diagnosis | PARTIAL | Streaming, invalid-schema repair, provider outage behavior, and deadline cleanup have regression coverage; live provider speed is unmeasured. |
| Repair proposal, approval, retry, verification | PARTIAL | Existing Failure workflow is retained; end-to-end repair journey not completed. |
| Browser/locator and recorder | PARTIAL | Existing recorder session and locator APIs are reused; browser E2E was blocked. Pending recorder creation is now closed if the view is disposed. |
| Debugger and AI assistance | PARTIAL | Existing Studio debugger/assistant remain in place; real Edit → Run → Debug journey not run. |
| Runtime event and workflow display | PARTIAL | Same persisted runtime/event data is summarized; model tests pass, live responsive review is missing. |
| Fake diagnosis fallback | WORKING at code level | Regression checks ensure provider outage is reported instead of fabricated success; this does not substitute for a live provider check. |

## Workspace changes

- Added a staged Workspace route that embeds the existing requirement, case, and failure workflows instead of adding a separate Agent Center.
- Preserved project/entity context in route links and refreshes.
- Added live task/run progress and a short evidence/next-action summary from persisted runtime data.
- Simplified the standalone failure page by 387 net tracked lines while extracting reusable evidence and overview views.

## Studio changes

- Removed the effect that opened the run/browser dialog whenever a run started.
- Kept a manual Browser action and existing run status indicators.
- Centered the run dialog and increased its maximum size to 1360×940; small screens use the available viewport. Kept the modal behavior in one style block instead of overriding a narrow-drawer rule later.
- Passed source node, failure, and run identifiers through the Studio link so the editor can reopen in failure context.

## Workflow changes

- Reused the existing persisted Runtime snapshot, event, polling/SSE mechanisms, and step data; no parallel runtime or event transport was added.
- Grouped sub-events by their actual step/runtime owner and coalesced token progress into the active diagnosis stage.
- Expanded the live event stream into available height when there is no TaskStep DAG.
- Kept event-level details available for inspection while presenting grouped summaries first.

## Removed complexity

- Removed automatic modal opening on every Studio run.
- Consolidated the run modal CSS and removed the obsolete side-drawer animation/overrides.
- Removed duplicated layout/selection code from the old Failures page (699 tracked lines removed there, 312 added back in the focused page; net −387).
- Kept one canonical Failure diagnosis entry point instead of starting another analysis flow from the Runtime Browser view.
- Added no new dependencies, provider registry, runtime, or SSE stack.

## Golden journey and click cost

The requested journeys A–F and the combined Golden Journey were not run in a browser. No before/after click or route-transition counts were captured, so those counts remain **unknown**. Workspace stages stay on one route by design, and route links preserve context, but that does not establish the actual interaction count.

The current implementation has focused automated coverage for URL context, runtime trace summaries, failure-state derivation, and streaming diagnosis. These checks do not prove that a first-time QA Engineer can finish the full workflow without documentation.

## Review and remaining debt

- Independent code review found no remaining P0/P1/P2 after fixes for auto-started diagnosis, recorder session cleanup, source context propagation, streamed-schema repair, and cleanup deadline handling. It retracted an earlier incorrect finding about WAITING being terminal.
- The previous review's low-risk timeout finding was fixed: `stream.aclose()` is now bounded by the remaining diagnosis deadline, with a regression test for a hanging close.
- Ponytail review: no second runtime/provider/event layer or dependency; the automatic run dialog behavior was deleted. The four shared helpers/contracts each serve multiple existing route/view callers (see Acceptance report).
- UI/UX review is **PARTIAL** because live screenshots at 1920×1080, 1440×900, and 1366×768 could not be captured.
- Remaining debt: run all six E2E journeys in a browser-enabled environment; conduct the first-time user and resolution reviews; measure actual provider latency; record real click/transition counts. The Monaco lazy chunk remains about 4.03 MB raw / 1.04 MB gzip after the successful build.

## Before/after summary

| Measure | Before | After |
|---|---|---|
| Requirement → Run clicks | Not measured | Not measured |
| Requirement → Run route transitions | Not measured | Not measured; the new staged flow remains on Workspace, but browser measurement is pending |
| Failure → Verify clicks | Not measured | Not measured |
| Failure → Verify route transitions | Not measured | Not measured; Workspace/Workflow/Studio links carry context, full journey pending |
| Studio run dialog | Automatically opened for a new run | Opens only from the explicit Browser action |
| Run view width | 560px maximum side drawer | 1360px maximum centered dialog |

See [`agent-experience-acceptance.md`](agent-experience-acceptance.md) for the acceptance status, validation results, and Ponytail Impact.
