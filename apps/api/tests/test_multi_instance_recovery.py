"""Startup recovery must not close work a live replica is still doing.

Each recovery below used to act on every unfinished row in the database. With one process that is
correct; with two it turns a peer's live work into a failure. A time window is the only evidence a
process can produce without a lease, so these tests pin it at both ends.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.container import get_requirement_lifecycle_service, get_task_runtime_service
from app.persistence.models import (
    AIInvocationORM,
    ProjectORM,
    QualityDiscoveryRunORM,
    RequirementORM,
    TaskORM,
    utc_now,
)
from app.repositories.ai_repo import AIRepository
from app.services.quality_discovery_service import QualityDiscoveryService

pytestmark = pytest.mark.integration


async def test_startup_recovery_leaves_a_fresh_requirement_analysis_alone(test_db_session):
    service = get_requirement_lifecycle_service()
    fresh = {"history": [{"id": "analysis_fresh", "status": "RUNNING", "started_at": utc_now().isoformat()}]}
    stale = {
        "history": [
            {"id": "analysis_stale", "status": "RUNNING", "started_at": (utc_now() - timedelta(hours=1)).isoformat()}
        ]
    }
    async with test_db_session() as session:
        session.add(ProjectORM(id="proj", name="Project"))
        await session.flush()
        session.add_all(
            [
                RequirementORM(
                    id="req_fresh",
                    project_id="proj",
                    title="Fresh",
                    description="",
                    acceptance_criteria="",
                    qa_model=fresh,
                ),
                RequirementORM(
                    id="req_stale",
                    project_id="proj",
                    title="Stale",
                    description="",
                    acceptance_criteria="",
                    qa_model=stale,
                ),
            ]
        )
        await session.commit()

    await service.recover_interrupted()

    async with test_db_session() as session:
        fresh_row = await session.get(RequirementORM, "req_fresh")
        stale_row = await session.get(RequirementORM, "req_stale")
    assert fresh_row.qa_model["history"][-1]["status"] == "RUNNING", "a peer's live analysis was closed"
    assert stale_row.qa_model["history"][-1]["status"] == "FAILED"


async def test_a_run_still_moving_in_another_replica_is_not_paused(test_db_session):
    async with test_db_session() as session:
        session.add(ProjectORM(id="proj", name="Project"))
        await session.flush()
        session.add_all(
            [
                QualityDiscoveryRunORM(
                    id="qd_fresh",
                    project_id="proj",
                    start_url="http://127.0.0.1:1/",
                    mode="EXPLORE",
                    status="RUNNING",
                    requested_by="owner",
                    result={},
                    created_at=utc_now(),
                    updated_at=utc_now(),
                ),
                QualityDiscoveryRunORM(
                    id="qd_stale",
                    project_id="proj",
                    start_url="http://127.0.0.1:1/",
                    mode="EXPLORE",
                    status="RUNNING",
                    requested_by="owner",
                    result={},
                    created_at=utc_now() - timedelta(hours=2),
                    updated_at=utc_now() - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()

    from app.repositories.quality_discovery_repo import QualityDiscoveryRepository

    async with test_db_session() as session:
        rows = await QualityDiscoveryRepository(session).list_non_terminal()
    stale = [
        row.id for row in rows if QualityDiscoveryService.is_stale_run(row, QualityDiscoveryService.STALE_AFTER_SECONDS)
    ]
    assert stale == ["qd_stale"], "a run another replica is still driving would have been paused"


async def test_a_live_task_and_a_live_provider_call_survive_a_peer_startup(test_db_session):
    async with test_db_session() as session:
        session.add(
            TaskORM(
                id="task_live",
                type="RUN_REGRESSION",
                goal="Still running",
                status="RUNNING",
                owner_id="owner",
                inputs={},
                context={},
                verification={},
                lease_owner="worker-a",
                lease_token=1,
                lease_expires_at=utc_now() + timedelta(seconds=60),
            )
        )
        await session.commit()
        session.add(
            AIInvocationORM(
                id="inv_live",
                task="failure_diagnosis",
                status="RUNNING",
                provider="openai-compatible",
                model="model",
                duration_ms=0,
                started_at=utc_now(),
                created_at=utc_now(),
            )
        )
        await session.commit()

    recovered = await get_task_runtime_service().scheduler.recover_interrupted()
    interrupted = await AIRepository().recover_interrupted_invocations()

    async with test_db_session() as session:
        task = await session.get(TaskORM, "task_live")
        status = (await session.get(AIInvocationORM, "inv_live")).status
    assert recovered == [], "a peer's live task was blocked by this replica's startup"
    assert interrupted == 0
    assert task.status == "RUNNING"
    assert status == "RUNNING", "a live provider call in another replica was reported as interrupted"
