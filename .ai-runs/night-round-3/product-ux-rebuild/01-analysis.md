# Live analysis — Northstar QA workbench

## Scope and safety

- Reviewed the running local app on `127.0.0.1:5174` and API on `127.0.0.1:8001`; authenticated with the documented local admin account and explicitly selected `Northstar · Golden Demo Shop` (`proj_golden_shop_v1`).
- Followed the existing workspace composition instead of proposing a second workflow/runtime. The workspace already hosts cases, embedded Automation Studio, run results, failure debugging, and AI Repair; run history remains a separate existing route.
- No AI/Jev call or repair apply is authorized for this UX pass. The selected `test_search` case is read-only against an ephemeral local demo-shop server; its execution may add the normal run record but does not modify tracked source or business records.
- Existing Round 3 accessibility work and inherited changes—including `mise.toml`—remain untouched.

## Confirmed friction

1. **Run configuration silently differs by entry point (P1).** `WorkspaceRunDock` sends the selected environment, region, browser, and worker count. The embedded Automation Studio play button calls `useRunExecution`, which omits all four for ordinary runs. It also says “execute tests in current file” although the existing selected-case binding takes precedence over the file. Users can therefore believe a run used their configured profile or a broader target than it did.
2. **Project context is repeated in the embedded editor.** The app-level navigation already owns project selection, while embedded Automation Studio renders another full project selector in its file sidebar. This adds a second navigation surface to the main workbench.
3. **The five-stage journey cannot fit tablet/narrow widths without internal horizontal scrolling.** The live stage rail reserves 140px per step (700px minimum plus padding); the earlier 360px/768px evidence shows the rail itself scrolls even though the page does not overflow. On narrow screens that hides workflow stages and their status context.
4. **End-to-end routes are connected, but the transitions are not self-evident.** The workspace run dock opens config/status actions, the Studio has a separate Play button, results expose logs/events/browser evidence, and failure context opens debugger/AI Repair. The existing project/run/case context is preserved; no new route or runtime is needed.

## Boundaries

- Keep the dock as the home for run configuration and workflow actions; make Studio quick-run consume that same config and label its actual target (selected case vs active file).
- Keep the standalone Studio project selector for its existing route; remove only the duplicate selector when Studio is embedded in the workspace.
- Compact the stage rail responsively without removing stages, statuses, keyboard access, or accessible names.
- Do not change test verdict ownership, AI/Jev invocation policy, repair approval, source-write paths, APIs, data, or run-history architecture.

## Before evidence

Existing baseline screenshots are under `evidence/before/`; the most relevant are `automation-studio-1440.png`, `test-explorer-1440.png`, `results-current-1440.png`, `runtime-live-browser-1440.png`, `debugger-1440.png`, `failure-repair-1440.png`, and the 360/768 failure layouts. Current-session DOM inspection also confirmed the duplicated embedded project selector, different run request construction paths, and mobile stage-rail overflow in the source/CSS.
