# Real AI + Jev Validation — Night Final Acceptance

## Result

**PASS for real provider availability, candidate evaluation, and proposal-only repair acceptance.** The workflow stopped at `PATCH_READY`; Apply and post-approval verification were not attempted.

## Provider Configuration (safe summary only)

- AI provider/model: `openai-compatible` / `deepseek-flash`.
- Jev provider/model: `jev` / `jev-1.13.0`.
- Configured credentials were present; no secret values were printed or recorded.
- Fallback was disabled for the acceptance. Both live acceptance paths reported no fallback.

## Evidence

- `AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1` — `test_live_ai_jev_repair_stops_at_approval_and_tests_candidate_in_sandbox`: PASS. The actual candidate test passed in the sandbox; state remained `PATCH_READY`.
- `AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1` — `test_live_ai_jev_failure_repair_through_browser_ui`: PASS. The browser flow reached `PATCH_READY`, reported no fallback, and left source unchanged.
- In the disposable API, `/api/ai/status` returned HTTP 200 with `real_model_available=true`, `fallback_active=false`, and streaming enabled.
- `/api/ai/system-health?refresh=false` reported an actual streaming response from DeepSeek and a valid Jev decision response from `jev-1.13.0`; both component checks were `ok`.
- The platform health check also launched system Chrome successfully. The overall health state was `degraded` only for missing Python LSP and zero remote workers; API-local execution was available.
- UI screenshots: `evidence/ai-jev-browser/desktop.png`, `tablet.png`, `mobile.png`, and `patch-ready.png`.

## Safety and Decision Boundaries

- No Apply endpoint/action was invoked. No approval was simulated.
- No repository source file changed. The synthetic manual failure/recovery test was in a temporary project workspace, not the repair-Apply path.
- AI/Jev did not assign test verdicts. The Golden Journey's FAILED/PASSED outcomes came from pytest execution.
- No autonomous or repeated repair loop was started.

## Follow-up Observation

The first disposable attempt explicitly disabled AI and Jev. Under that configuration, `/api/ai/status`, `/api/runs`, and `/api/failures` returned 500 while services constructed AI-dependent dependencies. The acceptance harness was then restarted with the configured real providers and all live probes passed. Disabled-provider mode remains a separate follow-up; it was not fixed or claimed as validated.
