# Request

Split `QualityDiscoveryService` by responsibility without behavior changes, verify existing tests remain green, then add a Discovery journey → replayable steps → pytest draft workflow through the existing human preview/adoption path. Generated source must pass assertion-bypass checks and must not be written to the workspace before human approval. Browser action permission remains determined by the existing deterministic policy; do not add a path that relaxes it.

- Primary route: refactor, then new feature.
- Risk: HIGH (large cross-cutting service refactor plus task/runtime integration and workspace-write boundary).
- Repository: `/Users/hans/Code/github/ai-qa-platform`, branch `main`.
- Initial working tree already contains many unrelated and prior uncommitted changes, including edits to Discovery code/tests, API, worker, frontend, and docs. Preserve them; do not stage, commit, or push.
- Run-log initializer referenced by the skill is absent at `scripts/init_run_log.py`; this run log is being maintained directly.
