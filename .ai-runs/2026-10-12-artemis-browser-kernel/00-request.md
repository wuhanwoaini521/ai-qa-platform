# Request

用户要求基于 ARTEMIS 理念升级 AI QA Platform 的 Web 执行内核，先审计真实架构，再继续开发；重点包括共享 Browser Runtime、真实 AI + Jev、Safety Net/Checker、Fast/Agent、失败恢复、长任务历史、工作区连续性、多入口内核和全链路验收。

- Primary task type: new-feature + reliability refactor (mixed)
- Risk: HIGH — execution engine, provider calls, browser safety, recovery, persistence, and UI verification
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Branch: `agent/ai-qa-platform-stability` (tracks `origin/main`)
- Starting HEAD: `8a7c6a4 fix: stabilize workspace state and locator repair`
- Initial worktree: not clean. Existing user changes include multiple Web workspace/results/i18n files, new frontend tests/models, audit reports, `.ai-runs` records, and `runtime/runtime/`. These are out of ownership and must be preserved and excluded from commits.
- Provider readiness: effective config reports real `openai-compatible` provider and Jev enabled with keys present. Secret values were not displayed or recorded.
- Compatibility boundary: preserve existing REST contracts and deterministic pytest/Playwright/Recorder/Debugger behavior; no fake provider may count as live AI + Jev acceptance.
