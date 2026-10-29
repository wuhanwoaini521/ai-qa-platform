# Conditional Recovery Transition with Optimistic Versioning

- **Knowledge Status:** EXPERIMENTAL (bounded SQLite and PostgreSQL 18.6 regression evidence; multi-process and production PostgreSQL 16 behavior NOT VERIFIED).
- **Topic:** Prevent stale recovery scans from overwriting a newer lifecycle state and keep durable status/event writes atomic.
- **Research Question:** How can an existing SQLAlchemy ORM recovery path avoid state regression without adding a scheduler, state table, or migration?
- **Source URL(s):** SQLAlchemy official tagged documentation: [Configuring a Version Counter / Simple Version Counting](https://github.com/sqlalchemy/sqlalchemy/blob/rel_2_0_54/doc/build/orm/versioning.rst) and [ORM UPDATE and DELETE with Custom WHERE Criteria / Important Notes and Caveats](https://github.com/sqlalchemy/sqlalchemy/blob/rel_2_0_54/doc/build/orm/queryguide/dml.rst). Project implementation evidence is at `apps/api/app/repositories/quality_discovery_repo.py`, `apps/api/app/services/quality_discovery_service.py`, and `apps/api/app/persistence/models.py` at baseline `245c00cacd946c8dea59991807af6b873fcdaf1d`.
- **Source Version:** SQLAlchemy `rel_2_0_54` (the project `uv.lock` resolves SQLAlchemy 2.0.54); AI QA Platform working tree baseline commit 245c00c plus this uncommitted mission diff.
- **License:** MIT for the pinned SQLAlchemy tag.
- **Verified Date:** 2026-10-28.

## Findings

**Source-verified SQLAlchemy facts:** The tagged versioning documentation describes `version_id_col` protecting per-object ORM flush UPDATE/DELETE operations and detecting stale row counts. The tagged custom-DML documentation states that this versioning mechanism does not apply to bulk multirow UPDATE/DELETE operations. These are documentation-backed SQLAlchemy 2.0.54 facts, not proof of any particular platform concurrency behavior.

**Platform pattern and evidence:** Recovery that scans candidate statuses and later writes a fixed status must re-check the state at the write boundary. This implementation adds an optional repository status precondition and uses the existing ORM version column/retry path; it snapshots the scanned status, changes to PAUSED only if that exact status still holds, and persists the pause event in the same DB transaction. It publishes in-process SSE projections only after commit. No schema/API contract change is made.

## Limitations

The reported SQLite and PostgreSQL test slice exercises scanned-state completion race handling and atomic event rollback within the existing service/repository test path. The PostgreSQL run used temporary PostgreSQL 18.6 (`embedded-postgres==18.6.3`); it does not establish behavior on production PostgreSQL 16. Neither database test establishes two concurrent API processes, multiple-process recovery startup policy, ownership/fencing of a still-active executor, or general exactly-once event delivery. The ORM versioning fact does not protect bulk multirow DML; direct/bulk SQL writers must be assessed separately. A local live event can still be missed by subscribers during process failure; the durable event remains in the persisted result snapshot.

## Applicability

Useful for bounded recovery of a known row when an existing versioned ORM is the source of truth. Not a substitute for worker leases, owner identity, fencing, multi-instance startup policy, or a durable cursor event store. Do not generalize into a new Runtime.

- **Evidence:** Source: SQLAlchemy `rel_2_0_54` versioning documentation, “Configuring a Version Counter / Simple Version Counting”; custom-DML documentation, “ORM UPDATE and DELETE with Custom WHERE Criteria / Important Notes and Caveats”; pinned tag license is MIT. Dependency provenance: project `uv.lock` resolves SQLAlchemy 2.0.54. Parent-run test evidence: in the mission worktree, `../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_discovery_task_runtime.py -q` passed 15 on SQLite; with `AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test`, the same command passed 15 on temporary PostgreSQL 18.6 (`embedded-postgres==18.6.3`). This covers scanned-state completion race and atomic event rollback within the existing service/repository test path only; it is not evidence for two concurrent API processes, leases, or production PG16.
- **Confidence:** High for the cited version-specific SQLAlchemy behavior and MIT tag license; Medium for the tested SQLite/PostgreSQL 18.6 service/repository slice; Low for multi-process and production PostgreSQL 16 guarantees.
- **Related Projects:** AI QA Platform; any SQLAlchemy service with versioned lifecycle records.
- **Next Review Condition:** Revisit when multi-process recovery or production PostgreSQL 16 support is claimed; require two-independent-process collision/lease coverage and a regression run on PostgreSQL 16 before strengthening those applicability claims.
