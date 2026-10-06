# Final Acceptance

Acceptance evaluates the requested outcome and the evidence, not merely whether a test command returned zero.

## Acceptance checks

1. Every requested behavior and explicit boundary is implemented.
2. Relevant targeted and functional verification ran; required integration and risk-based regression are acceptable.
3. Independent code review is complete; UI review is complete when applicable and available.
4. Unresolved P0 and correctness, safety, compatibility, regression, or security P1 blockers are zero for `PASS`.
5. Known limitations, unverified behavior, and accepted out-of-scope findings are documented with their impact and disposition.
6. The diff matches scope, contains no debug residue or secrets, and no unauthorized commit/push occurred.
7. Report the real `git status`; preserve pre-existing user changes.

## Verdicts

Use exactly one verdict: `PASS`, `PARTIAL`, or `FAIL`.

- **PASS** — requested scope is complete; required verification, review, and regression passed; no blocking correctness issue or material evidence gap remains. Documented P2/P3 suggestions outside scope do not by themselves block PASS.
- **PARTIAL** — most requested work is complete and no known blocker remains, but a material non-blocking limitation or required evidence gap remains. Example: UI implementation and automated checks pass, but real browser verification is unavailable.
- **FAIL** — requested behavior is incomplete or incorrect, a blocking test/regression remains failed, a root cause is unresolved, or a blocking review finding remains unfixed.

Do not report `PASS` when a required check was not run. Distinguish an unavailable check (`PARTIAL` when no defect is known) from a check that demonstrates broken behavior (`FAIL`).

## Report

Write `09-final-report.md` for an authorized delivery run. Summarize scope, verified outcomes, actual commands/results, review blockers and dispositions, regression, remaining risks, `git status`, and the verdict. Read-only work has no run log and is answered in the conversation.
