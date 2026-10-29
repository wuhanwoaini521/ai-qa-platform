# Engineering Backlog

Status transitions: `BACKLOG → READY → IN_PROGRESS → IN_REVIEW → IN_QA → DONE`; `BLOCKED` / `REJECTED` are explicit terminal/intermediate states. Evidence is linked; report-only historical claims are not current verification. No item below is being implemented automatically.

## Autonomous R&D Mission — AI R&D, research, and bounded Execution Core repair (2026-10-28)

- **Status:** IN_PROGRESS / PARTIAL; do not mark the Mission or Architecture Gate complete.
- **Authorized scope:** audit/upgrade the existing Pi team; establish a portable Markdown/Git knowledge base; verify P0 framework sources; perform bounded architecture challenge; fix a reproduced lifecycle defect within current Task Runtime/BrowserRuntime/DecisionService boundaries; no framework adoption, production migration, deployment or merge.
- **Team/knowledge:** Technology Scout, Knowledge Curator and Architecture Critic profiles plus portable team/research workflow are present. A cross-agent reuse experiment passed: Scout source-checked SQLAlchemy 2.0.54, Curator updated the existing pattern/index, and a fresh backend consumer ran a deterministic in-memory stale-write/bulk-DML experiment. Added a bounded temporary-infrastructure fallback and GitHub preview procedure to existing team instructions; no duplicate GitHub skill was created.
- **Research:** LangGraph 1.2.18/MIT, Browser Use 0.13.14/MIT, and Skyvern v1.0.56/AGPL-3.0 release/license/manifest facts were verified from official tag sources. This is metadata-only: no candidate install, browser comparison, compatibility run, provider spend or legal assessment. Remaining P1/P2 candidates are NOT STARTED.
- **Architecture:** one debate round recorded. Candidate A remains the current operating baseline; Candidate B is provisional and challenged; Candidate C/dependencies are DEFERRED. Architecture Gate remains **DEFERRED / NOT PASSED**.
- **Execution Core:** the existing recovery guard/event transaction passed the 15-case `test_discovery_task_runtime.py` suite on SQLite and disposable PostgreSQL 18.6. Do not extend this to production PG16 or multi-process Discovery recovery.
- **Sprint A/B:** focused recovery and event failure-injection tests pass on both databases; full lifecycle/state matrix and generic event/evidence contract remain incomplete.
- **Sprint C:** SQLite and PostgreSQL 18.6 suites pass for Worker crash recovery, cancellation, timeout, duplicate/late result rejection, evidence persistence, and two concurrent real Worker subprocesses. No lease/fencing generation or stale reassignment guarantee is established.
- **Sprint D:** 17 targeted Node status/live-model tests pass; no UI source changed, so desktop viewport review is N/A. Full Web suite, build, lint, typecheck and browser checks remain NOT RUN.
- **Sprint E:** Browser Use/Skyvern comparison is BLOCKED / NOT RUN; there is no available local model endpoint and no provider cost cap. Candidates remain uninstalled; Skyvern legal review and full compatibility remain open.
- **Mission / Architecture Gate:** still PARTIAL; Architecture Gate remains **DEFERRED / NOT PASSED**.
- **GitHub delivery:** user authorized a normal development-branch push and Draft PR against `main` after exact-path, remote-state, and external-write preview. The remote branch is currently absent, no PR exists, and no write has occurred. Exact 67-path stage and Code Review are complete. Release Engineer verdict is PARTIAL / not ready to merge (comprehensive credential scan and full gates remain incomplete); if delivered, use Draft only and record the caveats.
- **Evidence:** `docs/architecture-review/architecture-debate-2026-10-28.md`, `framework-p0-verification-2026-10-28.md`, `engineering-knowledge/`, `.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/11-continuation.md`, and the current `docs/agent-handoff.md` Mission entry.

## QA-001 — Prove real Run → Results → Debug workflow

- **Priority:** P0
- **Owner:** QA Automation Engineer (with one Frontend Engineer only if a reproduced defect requires a fix)
- **Reviewer:** `reviewer`
- **Dependencies:** disposable project/run/failure fixture; real API + worker + BrowserRuntime available
- **Scope:** From an isolated project, execute a real test and open the persisted passed/failed execution in Graphite Workspace Run Results, then enter Debug with exact context. Excludes AI repair, Recorder, external writes, and production data.
- **Acceptance:** real execution provenance/exit code; `projectId`, `runId`, and exact existing `nodeid` survive; selected result matches; no invented `stepId`; Enter activates the same action; fail/path evidence remains linked. Synthetic-fixture pilot is not a substitute.
- **Verification:** Added regression coverage for Dashboard href/project/file/fallback and selected-node handoff; real system-Chrome desktop flow; isolated API/Worker runtime and persistence. Exact commands and evidence are recorded in `.ai-runs/qa-001-real-runtime/evidence/isolated-runtime/13-final-verification.md`.
- **Status:** DONE (real runtime, acceptance-scoped QA, Independent Code Review, Design Review, and Release Gate complete; see evidence below).
- **Evidence:** `.ai-runs/qa-001-real-runtime/evidence/isolated-runtime/13-final-verification.md` records exactly two real isolated `POST /api/runs` Worker/PytestRunner executions: `run_29d2bef67284` PASSED and `run_40f7db3e80e6` FAILED, with persisted executions, completed jobs, failure `fail_789e940fb6c2`, and `AssertionError` traceback `tests/test_qa001_fail.py:2`. `FailureRecord.source_file/source_line` remain null; the nodeid-derived file route is preserved, no `stepId` is invented, and the UI does not imply a persisted exact failure line. Real system Chrome 150 at 1440×900 verified Dashboard → Results → Debug, Enter activation, and post-refresh project/run/node/file/source context; fresh screenshots are in `.ai-runs/qa-001-real-runtime/evidence/review-followup/`. Previous Sprint-001 web suite: 202 passed; TypeScript, targeted ESLint, and `git diff --check` passed (not rerun during final review). Independent Code Review: APPROVED WITH NOTES, with no Blocker/Major; Design Director: PASS; acceptance-scoped QA evidence: PASS; Release Gate: PASS. Non-blocking notes: selected runs older than the Workspace latest-eight list may lose `nodeid`; add future pagination coverage. Missing persisted source location is tracked separately in QA-006. Final review/runtime report: `.ai-runs/qa-001-real-runtime/evidence/review-followup/14-independent-review-and-browser-followup.md`. QA-002 remains READY and unstarted.

## QA-002 — Validate Recorder → generated automation → editable test

- **Priority:** P0
- **Owner:** QA Automation Engineer; Frontend/Backend Engineer assigned only after interface seams are confirmed
- **Reviewer:** `reviewer`; Design Director for any UI change
- **Dependencies:** controlled loopback site and disposable browser/runtime fixture
- **Scope:** Real UI browser start, capture steps, create/edit generated script, save in workspace; no static mocked recorder success.
- **Acceptance:** real BrowserRuntime session and observed recorded steps; correct project/case/binding context; generated source is edited in Monaco and persisted; errors/permissions are visible; the exact saved node is executed once by the real project-scoped Worker and verified in Results. The operator explicitly authorized that Worker execution for QA-002.
- **Verification:** real browser event evidence, API persistence assertions, relevant Recorder and web tests.
- **Status:** DONE (retained real BrowserRuntime → editable source → one Worker execution → persisted Results evidence passes; the authorized desktop remediation and all fresh architect/code, QA, Design, and Release gates pass. Historical Design FAIL/Release PARTIAL remain preserved; QA-003 is separately BLOCKED by missing BrowserRuntime page evidence after real provider readiness passed.)
- **Evidence:** `.ai-runs/qa-002-recorder-workflow/` records isolation, ACL fixes/reviews/tests, and the full workflow. Recorder ACL is independently approved; focused ACL suites passed 52 and 12 tests. Save & Open now returns 200 after the task-owned canonical workspace-key fix (provenance clarified in `00-request.md`). Real BrowserRuntime session `c2b284a56db44dfe840f1c4edf280974` stopped at revision 11 with five server-side steps and actual `Result: Mercury`. Case `tc_rec_3ec80e1d22bc00072aae1141b57b2` and ACTIVE binding `bind_d2e0a72b4843` are isolated-DB verified for the exact project/workspace/file/node. Studio Monaco saved a targeted title assertion; API readback matched the generated source plus exactly that edit, AST parse passed, SHA-256 `ea097d708cab09f92c235a8ca3c8268459ffa1e8a696c1efa9ff3c8a81c7a351`. Existing WorkerDaemon `04a641f6-92c4-48e4-a88a-354616049b3f` ran the exact node once via Runs UI **WORKER**: Run `run_b6416109d35e` PASSED (1/1), Job `fe8c30f5-98c6-44c2-ae63-dc43ab09bf33` COMPLETED, Execution `exec_d757984ca2c3` PASSED; API and SQLite agree; Worker stopped OFFLINE. Independent QA: PASS for retained functional evidence only (no replay); Design Director: FAIL (Major Monaco height and crowded/clipped Recorder steps panel; Minor stage palette transition); Release Engineer: PARTIAL/not ready. Reports: `evidence/{19-independent-design-review.md,20-independent-release-gate.md,21-independent-qa-review.md}`; full chain in `evidence/17-integrated-workflow-self-qa.md`. A narrowly scoped desktop remediation was subsequently authorized; current implementation and browser evidence are in `evidence/remediation/01-desktop-remediation-checkpoint.md` and `evidence/remediation/desktop-browser-after.json`. No Runtime replay or Worker rerun occurred. Fresh desktop follow-up, pinned Playwright 1.62.0 evidence, 202 frontend tests, architect/code OK, QA PASS, Design PASS, and Release PASS are recorded in `evidence/remediation/02-followup-gates.md` and `evidence/remediation/03-release-gate-and-closeout.md`. The accepted Worker execution was not replayed. QA-003 is separately BLOCKED; see its own evidence/report.

## QA-003 — Verify approval-gated AI repair with a real provider

- **Priority:** P0
- **Owner:** Backend Engineer (workflow/API) + QA Automation Engineer (verification)
- **Reviewer:** `reviewer`; Architect for runtime/security boundaries
- **Dependencies:** QA-001 real failure context; explicitly available healthy AI/Jev provider; human operator approval
- **Scope:** Real failure → analysis → proposal/diff preview → explicit human apply → exact-node verification. No provider mock as success, no auto-apply.
- **Acceptance:** provider identity/availability and input context recorded; analysis does not alter deterministic verdict; proposal differs from applied state until a human confirms; exact test rerun produces the recorded result; all artifacts/errors persist.
- **Verification:** real API/UI workflow and provider evidence; authorization, rejection/cancel, exact rerun tests.
- **Status:** BLOCKED after the first proposal-only integration attempt. Stage 1 real AI/Jev readiness passed; the isolated real pytest Run/Execution failed but returned no BrowserRuntime page-session controls, so analysis did not start and no proposal or approval state exists. Preserve provider-pass evidence; do not fabricate evidence or retry automatically.
- **Evidence:** prior handoff §3.22 says AI was not invoked; existing Round 6/9 evidence documents provider timeout/blocking, not a successful path. Current QA-003 intake/provider pass/implementation/blocked attempt are in `.ai-runs/2026-10-28-qa-003-real-ai-failure-repair/`; `05-qa-report.md` records exit 1 at the missing `browser_sessions` controls assertion. No analysis, verified proposal, human approval, exact verification, or apply audit is evidenced.

## QA-004 — Validate populated Debug / Locator observability and Graphite UX

- **Priority:** P1
- **Owner:** Design Director + QA Automation Engineer
- **Reviewer:** `reviewer`
- **Dependencies:** QA-001 fixture with real failure, screenshot/trace/runtime telemetry
- **Scope:** Locate the real failing node, inspect source/log/browser/locator evidence and preserve context across result/debug views at desktop sizes.
- **Acceptance:** failure details map to the exact run/node; Locator and browser telemetry correspond to real runtime output; loading/empty/error states are distinct; keyboard/focus works; design review passes at 1280×800, 1440×900, 1920×1080.
- **Verification:** real browser, API response IDs and trace/artifact cross-check; relevant Web tests; screenshots.
- **Status:** READY
- **Evidence:** current pilot verifies routing contract only; populated live Locator/Runtime evidence is NOT TESTED by Round 14.

## QA-005 — Prove cross-process Browser session resume/recovery

- **Priority:** P1
- **Owner:** Architect + Backend Engineer
- **Reviewer:** `reviewer`; QA Automation Engineer for recovery tests
- **Dependencies:** dedicated isolated API/worker runtime and explicit lifecycle contract
- **Scope:** Verify browser session lifecycle across API restart, reconnect/recovery, timeout/cancel, events, and cleanup. No new runtime layer.
- **Acceptance:** persisted state/restart semantics are explicit; no stale or duplicate session; timeout/cancel cleans owned resources; recovered session and SSE events match persisted truth.
- **Verification:** focused backend/Runtime tests, integration smoke with a real process restart, cleanup evidence.
- **Status:** READY
- **Evidence:** product roadmap and prior handoff mark cross-process Browser session takeover as partial/in-progress; latest Graphite round did not exercise it.

## QA-006 — Investigate missing FailureRecord source location from pytest traceback

- **Priority:** P2 candidate (triage separately; not a QA-001 blocker)
- **Owner:** Backend Engineer + QA Automation Engineer
- **Reviewer:** `reviewer`
- **Dependencies:** isolated real PytestRunner failure with traceback and persisted `FailureRecord`
- **Scope:** Determine why `FailureRecord.source_file/source_line` are null when pytest traceback contains a concrete file:line; persist only reliably extracted metadata. Do not infer persisted fields from `nodeid`, fabricate test data, or alter deterministic PASS/FAIL.
- **Acceptance:** A real isolated assertion failure with a traceback location persists the correct source file/line; cases with no reliable location remain null; UI keeps inferred nodeid file context distinct from persisted error-location metadata.
- **Verification:** focused backend extraction/persistence tests and real isolated Worker evidence; no broad backend regression unless separately requested.
- **Status:** BACKLOG (not started; QA-001 review only identified the follow-up; no implementation or test data was fabricated).
- **Evidence:** QA-001 `fail-run-result.json` has null source fields while its actual PytestRunner traceback includes `tests/test_qa001_fail.py:2`; this gap is independent from QA-001's accepted route-context criteria.

## UI-001 — Direction A Graphite fidelity across desktop view states

- **Priority:** User-directed; no separate rank assigned.
- **Owner:** Frontend Engineer + Design Director; QA Engineer and independent `reviewer` for gates.
- **Reviewer:** `reviewer`; Design Director for visual acceptance; Release Engineer for integration.
- **Dependencies:** Approved Direction A Pencil frames, real before-state browser captures, and isolated local browser/app services.
- **Scope:** Ten view states grouped into nine page families: Dashboard; Workspace Debug and Explore; Projects; Requirements; Test Explorer; Write Tests; Results; AI Repair; Quality. Desktop only at 1280×800, 1440×900, and 1920×1080. User explicitly authorized extending the earlier Dashboard/Debug/Explore Graphite boundary to the remaining named views. No new page IA, API/runtime/Worker changes, business-semantics changes, mobile work, external writes, commit, push, or deployment.
- **Acceptance:** All named states use existing Graphite tokens/shell; design composition follows Pencil where a matching frame exists and real before screenshots/React behavior elsewhere; no unintended clipping/page-level horizontal overflow; text/status/focus remain legible; all existing routes, data/actions, URL context, deterministic verdicts, and human approval behavior remain unchanged. Synthetic fixture outcomes remain clearly non-live.
- **Verification:** Route-by-route real React browser After screenshots and interaction review at all three target sizes; Web test/typecheck/lint/build, i18n and diff-check; independent Code Review, QA, Design Director, Release gates.
- **Status:** DONE — implementation and required verification/review gates are complete. Release Engineer: PASS WITH NOTES, recommends closure. Independent QA is PARTIAL due remaining dense but readable Results panels at 1280px and pre-existing Chinese BrowserRuntime error detail in the English-locale Explore capture; Design Director: PASS WITH NOTES; final Code Review: OK, no issues. These are documented follow-up observations, not blocking Graphite/layout defects.
- **Evidence:** `.ai-runs/2026-10-27-graphite-fidelity-recovery/02-implementation-plan.md`; independent gates: `.ai-runs/2026-10-27-graphite-fidelity-recovery/evidence/review/final-independent-gates.md`; 30 actual React after captures and smoke manifests under `.ai-runs/2026-10-27-graphite-fidelity-recovery/evidence/after/`; focused source diff SHA-256 `80d4669895a2eec3fdd57a5b9aa9698a94d35f0e417f319d0c1c96d194ce97db`. Latest frontend checks: 202 tests passed, typecheck, lint, build, i18n (26 namespaces, 2 languages, 3416 keys), and `git diff --check` passed; existing Monaco bundle-size warning only. Synthetic fixture is labeled NOT LIVE and is visual evidence only.

## UI-002 — Graphite Developer Workspace journey and Quality metric verification

- **Priority:** User-directed; follows UI-001.
- **Owner:** Frontend Engineer with Design Director; QA Engineer, independent `reviewer`, and Release Engineer for gates.
- **Scope:** Improve the real desktop Workspace Results layout and Results/Debug/AI Repair context continuity, Write Tests workflow context, and Quality metric labels/definitions at 1280×800, 1440×900, and 1920×1080. Reuse existing Graphite shell/tokens, Workspace state/routes/services, and repair approval lifecycle. No new shell, runtime, route, or business workflow. No mobile work, AI/provider invocation, QA-003 Apply/Verify, test/run/record/save action, external write, commit, push, or deploy.
- **Acceptance:** Actual React before/after captures; Results and AI Repair preserve existing evidence and actions; browser checks demonstrate existing project/case/run/failure/node/file context across mode transitions without non-GET writes; Write Tests is reviewed with a clearly synthetic in-memory multi-line Python editor buffer (no save/run); Quality explanations match verified backend definitions and an isolated API regression checks score thresholds/aggregate. Required frontend gates and independent Code Review, Design, QA and Release gates are recorded. Synthetic fixture does not establish product runtime/provider/quality evidence.
- **Status:** DONE WITH NOTES — scoped UI work and applicable local/browser/review gates completed. Results, context continuity, Write Tests, and Quality passed; AI Repair acceptance is PARTIAL because no live proposal/approval flow was generated (explicitly out of scope). Debug runtime/LSP was not tested. Design is PASS WITH NOTES; Code Review is OK; Release recommends closure. QA-003 Apply/Verify remains BLOCKED.
- **Evidence:** `.ai-runs/2026-10-28-ui-002-workspace-journey/00-request.md`, `01-implementation-plan.md`, `evidence/after/desktop-acceptance.json`, 15 desktop after screenshots, and `evidence/review/final-independent-gates.md`. Final Web tests 203/203, typecheck, lint, build, i18n (26 namespaces/2 languages/3417 keys), focused API test (1 passed/15 deselected), Ruff check/format, and `git diff --check` passed. Browser captures use synthetic fixture data only; final route guard blocked all 27 non-GET attempts locally.
