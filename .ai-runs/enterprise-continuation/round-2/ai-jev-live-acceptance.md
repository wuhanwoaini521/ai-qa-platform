# Round 2 · Real AI + Jev failure-repair acceptance

Date: 2026-10-16 · WSL2 Ubuntu · branch `agent/wsl-continuation` · test workspaces and databases isolated per pytest case; local-only checkout page

## Successful live API acceptance

Command:

```bash
AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1 uv run --no-sync pytest \
  apps/api/tests/test_live_locator_repair_acceptance.py::test_live_ai_jev_repair_requires_approval_and_exact_rerun \
  -v --no-header -s -p no:cacheprovider -o addopts=
```

Result: **1 passed in 36.30s**. This used the configured live AI provider and Jev; neither fell back. Evidence emitted by the test:

- AI: provider `openai-compatible`, model `mimo-v2.6-flash`, 15,573 ms, fallback `false`; diagnosis `LOCATOR_CHANGED`.
- Jev: provider `jev`, model `jev-1.13.0`, candidate `candidate_1`, confidence `1.0`, 362 ms, fallback `false`; selected `get_by_role("button", name="Complete order", exact=True)`; Playwright candidate verification `true`.
- Before explicit human apply, the workspace source remained byte-identical. The test then explicitly approved/applied the proposal, reran the exact nodeid, required `PASSED`, and asserted persisted `patch.applied`, `verification.started`, `verification.completed`, `repair.verified` events.

## Successful real browser workflow

Command:

```bash
AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1 \
AI_QA_FAILURE_UI_SCREENSHOT_DIR="$PWD/.ai-runs/enterprise-continuation/round-2/screenshots/failure-ui" \
uv run --no-sync pytest \
  apps/api/tests/test_live_locator_repair_acceptance.py::test_live_ai_jev_failure_repair_through_browser_ui \
  -v --no-header -s -p no:cacheprovider -o addopts=
```

Result: **1 passed in 46.51s** on the semantically explicit, isolated checkout page. Real AI diagnosed `LOCATOR_CHANGED` with `fallback=false`; real Jev selected the semantic Complete order locator with confidence `1.0` and `fallback=false`. The actual React UI flow required human Apply, then the exact rerun reached `VERIFIED` / `PASSED`; a human rollback restored the original source byte-for-byte and the UI persisted `ROLLED_BACK`.

Screenshots (real Playwright, 1440/768/360 initial viewports plus workflow states):

- `screenshots/failure-ui/desktop.png`
- `screenshots/failure-ui/tablet.png`
- `screenshots/failure-ui/mobile.png`
- `screenshots/failure-ui/patch-ready.png`
- `screenshots/failure-ui/verification-in-progress.png` (captured while the UI shows the verification run queued/in progress)
- `screenshots/failure-ui/real-rollback.png`

A user-level Noto Sans CJK font was installed from the Ubuntu `fonts-noto-cjk` package into `~/.local/share/fonts/noto-cjk/` after the first screenshots showed tofu glyphs. No system-level configuration was changed; screenshots above are readable Chinese after `fc-cache` refresh.

## Race and stability findings

- The live browser test previously observed `repair-workflow=BLOCKED` while the associated analysis was still `RUNNING`; it broke early and failed despite the DB later showing a completed proposal. Fixed only the test synchronization: poll until analysis is terminal *and* workflow state is settled; fail with last observed status/state if the 180-second bound expires. Final passing browser run exercised this path.
- A real low-confidence run (`confidence=0.6`, below configured minimum) correctly blocked apply and preserved original source; the browser UI displayed the confidence block. This is evidence for the fail-closed branch, not the high-confidence path.
- A later fixture variant with a Cancel decoy was classified by the live AI as `TEST_DATA_ERROR` / `NOT_APPLICABLE` instead of `LOCATOR_CHANGED`; the test appropriately failed rather than treating it as success. The full-chain fixture was kept semantically explicit to avoid conflating diagnosis correctness with distractor noise. This demonstrates classifier sensitivity to page/context and remains a product risk; do not claim broad ambiguity handling is proven.
- The most recent rerun after moving the post-verification screenshot capture was safely blocked because the real provider returned `AI provider unavailable` (`repair.failed`, `block_reason=WORKFLOW_ERROR`), with no proposal or write. It did not invalidate the separate successful full-chain runs above, but provider availability is not stable and this rerun did not exercise the verification screenshot line.

## Regression and review

- Failure/run-workflow regression: `uv run --no-sync pytest apps/api/tests/test_failure_workflow.py apps/api/tests/test_runs_and_failures.py apps/api/tests/test_live_locator_repair_acceptance.py -q --no-header -p no:cacheprovider` → **102 passed, 3 skipped**; 5 existing pytest collection warnings for model/ORM types named `Test*`.
- Independent review found the need for terminal-state polling plus an explicit timeout. The current test has both. Reviewer also noted the one-target fixture reduces candidate ambiguity; this is disclosed above, and a prior low-confidence run demonstrates fail-closed behavior. No product code was changed in this test-hardening subtask.

## Remaining scope

This evidence verifies real failure→AI→Jev→human approval→patch→exact browser rerun→human rollback. It does not close the complete 11-case repair matrix (especially apply failure, verification failure, duplicate approval, interrupted session), Discovery→Coverage, PostgreSQL, Worker/Jenkins cluster, whole-site interactive UI, or final full regression. See `round-2/implementation-log.md` and `docs/agent-handoff.md`.
