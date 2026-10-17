# Golden QA Journey — User-Acceptance Evidence (browser only)

Branch `agent/ui-workspace-redesign` @ HEAD 23e73ab · project `proj_golden_shop_v1` ("Northstar · Golden Demo Shop")
Env: web http://127.0.0.1:5173 , api http://127.0.0.1:8000 (admin@ai-qa.local), Playwright 1.62.0, headless Chromium.
No repo source modified, no commits. Evidence: `journey.json`, `fixup.json`, `s10.json`, `repeatability.json`, `dock_state.json`, `screenshots/`.
Caveat: the first repeatability pass used a broken dock-detector (its `dock_present=false` rows are invalid); `dock_state.json` is the authoritative dock measurement.

## 1. Per-step table

| # | Step | Action (UI) | Result | Dur | Nav | Obstacle / defect | Evidence |
|---|------|-------------|--------|-----|-----|-------------------|----------|
| 1 | Open requirement | UI login → 侧栏 QA 工作台 → 需求 stage; requirement in URL | OK: REQ-001 + AC-001 rendered | 4.1 s login + 2.0 s | 1 | none | `screenshots/j00_login.png`, `j01_requirement.png` |
| 2 | AI analysis of requirement (real provider) | Click 让 QA Agent 分析需求 | **FAILED HONESTLY, but late**: 90 s with no alert/inline error → recorded as hang-like. The task's record never terminates (status stays RUNNING); the underlying provider errors (`RuntimeError("AI provider unavailable")`, `packages/qa_core/ai/provider.py:900`). No silent fake produced. | 91.1 s | 1 | **Defect D2**: no explicit failure notice inside 90 s; orphaned RUNNING task record | `j02_requirement_ai.png` |
| 3 | Review generated cases | Stage rail → 用例 | OK: TC-001…TC-009 listed | 1.7 s | 1 | none | `j03_cases.png` |
| 4 | Inspect a case | Open TC-004 | OK: steps + oracle shown | 1.7 s | 1 | none | `j04_case_detail.png` |
| 5 | Automation script is the real file (targets `add-to-cart`) | Stage rail → 自动化; open `pages/shop.py` / `test_shop.py` in Monaco | OK: real file. Monaco ready 1.9 s (typ. 2.9 s, worst 3.8 s). The green page object uses `get_by_role("button", name="Add to cart")` (confirmed by the passing run's step events, see #7); the intentionally-red `test_known_locator.py` still contains `locator('[data-testid="legacy-add-cart"]')` | 5.7 s | 1 | none | `j05_studio_file.png`, `j05b_studio_file.png` |
| 6 | Run the script from Studio (no destructive edit) | 运行文件 (`tests/test_shop.py`) | OK: run `run_90015e2152c5` PASSED 7.9 s | 10.8 s | 1 | none | `j06_run_from_studio.png` |
| 7 | Find the run result in the UI | Run dock (overlay) auto-opens 0.48 s after click; wait for terminal | OK: 已完成 / PASSED, per-step 实时事件流 (30 events: `浏览器操作 · 点击 · internal:role=button[name="Add to cart"] · 通过 · <100ms`), tabs 概览/逐条结果/流程图/时间线/执行追踪/浏览器/制品 | dock terminal 11.2 s | 1 | **Defect D5**: the plain result view summary is thin (`PARTIAL: summary incomplete`); full detail only in the dock | `dock_after_run.png`, `j07_run_result.png`, `j07b_run_record_page.png` |
| 8 | Open the intentionally-red failure + its evidence | Open `tests/test_known_locator.py` → 运行文件 → result surface | OK-ish: `run_1953951cf4db` FAILED (3.4 s); exception banner, locator text, stack hint and a screenshot preview are reachable | 20.4 s | 1 | failure text not on the first result tab (needed 制品/源码) | `j08_failure_evidence.png`, `j08b_result_stage.png`, `j08c_artifact_preview.png` |
| 9 | Debug surface shows failure location | 调试 tab on the failed run | **PARTIAL**: stack + variables render, but the failing **file:line is not shown in 调试** (only in the 源码 tab); empty states otherwise | 3.8 s | 1 | **Defect D3** | `j09_debug.png`, `15_full_stack.png` |
| 10 | AI diagnosis surface, triggered from UI | Failure tab → 开始 AI 分析 | **Honest failure, no fake**: the surface exists and starts the analysis; when the workflow reaches terminal BLOCKED the UI says "AI provider unavailable" / "AI 分析未成功，工作流已阻塞，尚未进入 Jev 决策。" (i18n `workspace.json:413`). But: this run's analysis got stuck, and after reload the panel shows stage 2 as **未启动** with **no action button at all** | trigger 4.0 s; wait 200.8 s | 1 | **Defect D1** (dead end) | `j10_ai_diagnosis.png`, `j10b_ai_diagnosis_final.png`, `j10c_before_ai.png`, `j10d_ai_terminal.png` |
| 11 | Repair proposal / suggested patch surface | Repair section on the same surface | Partial: "尚未生成代码补丁 Diff" placeholder is there; **no patch/approve/apply button is rendered** (correct, since no proposal exists) | 0.07 s | 0 | no proposal because AI blocked | `j11_repair.png`, `j11b_repair_final.png` |
| 12 | Can a repair be approved in an isolated scenario | — | **NOT EXERCISABLE**: needs a successful AI patch proposal (unreachable provider). Static only: apply is gated behind a 批准并应用补丁 button shown only when `repair.allowed_actions` contains APPLY; `POST /api/failures/{id}/analyses/{aid}/apply` exists | — | 0 | blocked by environment | `j11_repair.png` |
| 13 | requirement→case→automation→run→result linkage | Workspace stage rail + case detail | OK: rail shows 需求 1 / 用例 9 / 自动化 8-9 已绑定 / 结果 本次运行 PASSED · 已保存 8/8 逐例结果; case→script binding and run/exec ids visible | 0.07 s | 0 | per-case script link only for the selected case | `j13_linkage.png` |
| 14 | Whole-journey cost | — | clicks = **16**, URL changes = **9**, full page loads = **16** | — | 9 | — | `journey.json` |

Live-vs-recorded state check for a terminal failure (`fail_3598c42c2649`): `/analyses` → `FAILED`, repair-workflow `state=BLOCKED`, `allowed_actions=['START_ANALYSIS']`, `block_reason=WORKFLOW_ERROR` → UI correctly showed a 重新分析 retry. So the retry path exists only for the BLOCKED shape, not for the stuck shape (D1).

## 2. Repeatability — core flow (open case → run script → see result) ×3

| Run | Script | Status (UI) | Monaco | Click→dock visible | Dock→terminal | Duplicate runs | State lost? | Chromium leak |
|-----|--------|-------------|--------|--------------------|---------------|----------------|-------------|---------------|
| 1 | `test_shop.py` | PASSED (`run_c70eab49c8a0`) | 2.87 s | 0.48 s (measured on the probe run) | 11.2 s | 0 (7→8) | No: after reload the case + `test_shop.py` was still selected, overlay closed cleanly | 0 |
| 2 | `test_shop.py` | PASSED (`run_3c8f35e26e67`) | 2.90 s | — | — | 0 (8→9) | No | 0 |
| 3 | `test_shop.py` | PASSED (`run_655c51971359`) | 2.84 s | — | — | 0 (9→10) | No | 0 |
| (probe) | `test_shop.py` | PASSED (`run_c7ea1e5e22e8`), dock kept its state after 5 s | 2.9 s | 0.48 s | 11.2 s | 0 | dock state kept; overlay re-close + reload OK | 0 (0→0) |

Failure rate: **0/4 unexpected failures** (3/3 repeats PASSED). The only FAILED run is the intentionally-red `test_known_locator.py` (1/1, expected). No duplicated results, no lost state, no leaked browser process, no orphaned session observed. One transient `ps` count inflation was traced to processes left behind by my own killed diagnostic scripts (not the app); after cleanup, before/after counts were 0/0.

## 3. UX questions asked

- **Sidebar /runs and /quality lose the workspace?** Yes. Clicking 运行 → `/runs` and 质量洞察 → `/quality` both drop the workspace stage rail (`workspace_rail_present=false`); only the project chip survives. Context loss for the golden linkage story.
- **Time until Automation Studio is usable?** Monaco is interactive ~2.9 s after navigation (best 1.9 s, worst 3.8 s); the run dock appears 0.48 s after 运行文件.
- **录制 entry inside Studio?** No. The Studio toolbar has only 保存 / 校验 / 运行文件 / 调试. Recording lives on a separate page (开始录制 / 选择元素 / 生成脚本 / 保存为 Case 并运行), reachable from the top navigation, not from Studio.

## 4. Defects ranked by impact

1. **D1 (High) — repair analysis can wedge the UI into a dead end.** A client disconnect mid-analysis leaves server state `analysis.status=RUNNING` / repair-workflow `state=ANALYZING`, `allowed_actions=[]` (`/api/failures/fail_10c452192e05/analyses`, `/repair-workflow`). On reload the workspace renders stage 2 as **未启动** and hides *every* action (no cancel, no retry, no approve) — the UI and the API contradict each other. Evidence: `j10b`, `j10c`, `j10d`, `dock_state.json`, probe output.
2. **D2 (High) — AI analysis gives no explicit failure notice for 90 s+.** The requirement analysis ran 91 s with no alert or inline error, and its task record never leaves RUNNING, so the 执行观察台 can show "运行中" indefinitely. Evidence: `j02_requirement_ai.png`.
3. **D3 (Medium) — the 调试 (debug) surface does not show the failing file:line** for a stored failure; the location appears only in the 源码 tab, and stack/variables are empty-state. Evidence: `j09_debug.png`.
4. **D4 (Medium) — sidebar leaves the workspace** for 运行 / 质量洞察: stage rail disappears (`/runs`, `/quality`) → context loss. Evidence: `fixup.json → sidebar_context`, `j19_quality_page.png`.
5. **D5 (Low-Med) — the result surface summary is thin**: status/duration are there but per-case/per-step detail requires the modal dock (逐条结果) or a separate 运行记录 page. Evidence: `j07_run_result.png`.
6. **D6 (Low) — no 录制 entry point inside Automation Studio**; users must leave Studio for the recorder page. Evidence: `dock_state.json → studio_buttons`, `j18_studio_recorder.png`.

## 5. What could NOT be verified, and why

- **Step 12 (approving a repair in an isolated scenario)** and any patch diff/apply UI: requires a successful AI root-cause analysis and patch proposal; the provider is unreachable from this environment, so no proposal was ever generated (workflow blocks with `WORKFLOW_ERROR`). Only static gating evidence exists (`允许的动作`/`批准并应用补丁` rendered solely for `allowed_actions` containing APPLY).
- **The success path of AI analysis** (requirement analysis, root-cause, patch suggestion) — same reason; only the honest-failure path could be observed.
- **Deep Studio editing/校验 semantics** — not in scope of the 14 steps; only 运行文件 was exercised.
- Numbers above come from one environment lane; heavy suites (pytest/builds) were intentionally not run, per the light-load constraint.
