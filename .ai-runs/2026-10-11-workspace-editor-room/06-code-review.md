# Code Review

Structured second pass over the changed lines and their call sites (no separate reviewer tool available).

- Correctness: stage-specific collapse handles direct automation links and stage transitions; the header toggle remains usable. Media-query changes update the embedded file-tree default without removing the manual toggle.
- AI state: the badge now depends on `run.failed` plus a recognized structured `failure_reason`, not on failure presence alone. Generic operation errors and output/validation failures remain separate from provider outages; explicit provider errors remain recognized. Generic stream errors now use provider-neutral advice.
- Compatibility/security: no public API, persistence schema, auth behavior, secrets, or backend changes. Session layout remains in existing session storage.
- Duplication/complexity: reuses existing collapsible panels and adds one pure classifier with focused unit tests.
- Blockers: none found. Remaining limitation is the local Python language server environment; `basedpyright` is declared but unavailable after its dependency build failed.
