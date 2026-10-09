from __future__ import annotations

from app.ports.browser_runtime import BrowserRuntime
from app.ports.task_unit_of_work import TaskUnitOfWorkFactory
from app.services.task_command_service import TaskCommandService
from app.services.task_execution_orchestrator import (
    TaskExecutionOrchestrator,
    active_runtime_step,
    active_task_deadline,
)
from app.services.task_scheduler_service import TaskSchedulerService

__all__ = ["TaskRuntimeService", "active_runtime_step", "active_task_deadline"]


class TaskRuntimeService:
    """Composition and lifecycle entry point for task commands and the scheduler."""

    def __init__(
        self,
        *,
        repository_scope: TaskUnitOfWorkFactory,
        concurrency: int = 2,
        poll_interval: float = 0.5,
        browser_runtime: BrowserRuntime | None = None,
    ) -> None:
        self.execution = TaskExecutionOrchestrator(
            browser_runtime=browser_runtime,
            repository_scope=repository_scope,
        )
        self.scheduler = TaskSchedulerService(
            self.execution,
            concurrency=concurrency,
            poll_interval=poll_interval,
            repository_scope=repository_scope,
        )
        self.commands = TaskCommandService(
            goal_service=self.execution.goal_service,
            max_task_calls=self.execution.ai_service.max_task_calls,
            cancel_execution=self.scheduler.cancel_active,
            repository_scope=repository_scope,
        )

    async def start(self) -> None:
        await self.scheduler.start()

    async def stop(self) -> None:
        await self.scheduler.stop()
