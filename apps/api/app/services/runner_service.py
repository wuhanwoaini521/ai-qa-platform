from __future__ import annotations

from integrations.jenkins_runner import JenkinsConfig, JenkinsRunnerBackend
from project_model.models import (
    RunnerHealthStatus,
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfileUpdate,
    RunnerType,
)
from qa_core.execution.runner_backend import LocalRunnerBackend

from app.persistence.models import RunnerProfileORM
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.settings import get_config


class RunnerService:
    def __init__(self, runner_repo: RunnerProfileRepository | None = None) -> None:
        self.runner_repo = runner_repo or RunnerProfileRepository()
        self.local_backend = LocalRunnerBackend()

    def _to_dto(self, orm: RunnerProfileORM) -> RunnerProfile:
        return RunnerProfile(
            id=orm.id,
            project_id=orm.project_id,
            name=orm.name,
            type=RunnerType(orm.type),
            enabled=orm.enabled,
            config=orm.config or {},
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_runners(self, project_id: str | None = None) -> list[RunnerProfile]:
        orms = await self.runner_repo.list_profiles(project_id=project_id)
        return [self._to_dto(orm) for orm in orms]

    async def get_runner(self, profile_id: str) -> RunnerProfile | None:
        orm = await self.runner_repo.get_by_id(profile_id)
        return self._to_dto(orm) if orm else None

    async def create_runner(self, data: RunnerProfileCreate) -> RunnerProfile:
        orm = await self.runner_repo.create_profile(data)
        return self._to_dto(orm)

    async def update_runner(self, profile_id: str, data: RunnerProfileUpdate) -> RunnerProfile | None:
        orm = await self.runner_repo.update_profile(profile_id, data)
        return self._to_dto(orm) if orm else None

    async def delete_runner(self, profile_id: str) -> bool:
        return await self.runner_repo.delete_profile(profile_id)

    async def check_health(self, profile_id: str) -> RunnerHealthStatus:
        if profile_id == "local":
            return await self.local_backend.check_health()

        runner = await self.runner_repo.get_by_id(profile_id)
        if not runner:
            raise ValueError(f"Runner profile with ID {profile_id} not found.")

        if not runner.enabled:
            return RunnerHealthStatus(
                runner_id=runner.id,
                type=RunnerType(runner.type),
                status="DISABLED",
                message="Runner profile is disabled.",
                base_url=runner.config.get("base_url"),
            )

        if runner.type == RunnerType.JENKINS.value:
            integration = get_config().integrations.jenkins
            global_config = integration if integration.enabled else None
            config = JenkinsConfig(
                base_url=runner.config.get("base_url") or (global_config.base_url if global_config else ""),
                job_name=runner.config.get("job_name", "qa-suite"),
                user=runner.config.get("user") or (global_config.username if global_config else None),
                api_token=runner.config.get("api_token")
                or (global_config.token.get_secret_value() if global_config else None),
            )
            backend = JenkinsRunnerBackend(config=config)
            return await backend.check_health()

        return await self.local_backend.check_health()
