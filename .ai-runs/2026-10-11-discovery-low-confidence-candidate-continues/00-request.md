# Discovery Low-Confidence Candidate Continues

- run-date: 2026-10-11
- task-type: bug-fix
- scale: standard
- risk: HIGH (browser-exploration orchestration and persisted frontier behavior)
- repository: `/Users/hans/Code/github/ai-qa-platform`
- branch: `main`
- initial status: working tree contains prior unrelated modifications and the previous headless-browser fix; `quality_discovery_service.py` and `test_quality_discovery.py` were clean at start.

## Original Request

“DiscoveryBlocked: Jev 未返回可执行的候选动作。探索还是有问题。”

## Scope

Correct discovery behavior when Jev returns a candidate but the decision is rejected for low/missing confidence. Do not lower the confidence threshold or execute a rejected action. Preserve the required-Jev safety gate for provider failures without a usable attempted candidate.
