# Request

- Task: AI QA Platform Runtime Reliability & Architecture Hardening
- Type/scale: multi-area implementation + full-project validation; large/high risk
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Initial branch/HEAD: `main` / `0bed9db23d97a8182421032b15d3d0968754e498`
- Initial tracked working tree: clean
- Scope: baseline reproduction; config/provider health; Worker concurrency/lifecycle/capabilities and tests; service-boundary review; real AI + Jev and failure-repair journeys; security/config boundaries; frontend regression; final review.
- Safety: preserve user runtime data and configured credentials; do not run a Worker against unknown pre-existing queued jobs; no secret values in records.
