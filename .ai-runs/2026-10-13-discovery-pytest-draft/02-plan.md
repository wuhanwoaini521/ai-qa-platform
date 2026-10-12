# Plan

## Milestone 1 — behavior-preserving split

1. Move Discovery request/status/analysis schemas into `quality_discovery_models.py`, re-export them through the existing `quality_discovery_service.py` module.
2. Extract execution/planning/policy, graph/evidence persistence, and quality projection methods into focused mixins/modules; keep the existing service class as the compatibility composition root.
3. Preserve the current working-tree implementation, public method names, JSON formats, deterministic safety predicates, and existing monkeypatch/config seams.
4. Run focused Discovery/task/recorder suites, then the repository test and lint commands before proceeding to feature changes.

## Milestone 2 — Discovery journey pytest draft

1. Reconstruct replayable `RecorderStep`s only from persisted successful, state-changing Discovery edges and source-observed controls; reject unsupported/ambiguous actions and absent grounded assertion evidence.
2. Add a project-authorized endpoint/action that creates a `CREATE_TEST` task with recorded steps and assertion-policy opt-in, with no browser URL or browser session input.
3. Apply existing Python source safety and assertion-bypass validators; await Task Runtime's existing approval diff. No workspace write before explicit approval.
4. Add UI action from a completed Discovery journey to the existing runtime task/approval view.
5. Test approval/no-write, unsafe source rejection, candidate guard invariance, project/task authorization, and run relevant regression/lint.

## Acceptance

- Existing tests pass unchanged through Milestone 1 (only test patches needed if a test seam truly moved, and compatibility should be preferred).
- Discovery journey creates replayable pytest proposal through existing Task Runtime; no new browser policy path.
- Assertion bypass proposals are rejected and generated drafts wait for human approval.
- Workspace content is unchanged before approval; explicit approval uses existing guarded write path.
- No stage, commit, or push.
