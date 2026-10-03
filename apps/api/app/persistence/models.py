from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.persistence.database import Base
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JsonList(TypeDecorator):
    """Platform-independent JSON List column for SQLite and PostgreSQL."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if not value:
            return []
        try:
            return json.loads(value)
        except Exception:
            return []


class JsonDict(TypeDecorator):
    """Platform-independent JSON Dict column for SQLite and PostgreSQL."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}


class UtcDateTime(TypeDecorator):
    """Timezone-aware UTC ``DateTime`` behaving identically on SQLite and PostgreSQL.

    SQLite stores ``DateTime(timezone=True)`` as a naive string and hands naive
    datetimes back, while PostgreSQL returns aware ``timestamptz`` values.
    Normalising on bind and on result keeps comparisons and API payloads
    independent of the backend.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    framework_type: Mapped[str] = mapped_column(String(50), default="playwright_python")
    demo_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    requirements: Mapped[list[RequirementORM]] = relationship(
        "RequirementORM", back_populates="project", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list[TestCaseORM]] = relationship(
        "TestCaseORM", back_populates="project", cascade="all, delete-orphan"
    )
    workspaces: Mapped[list[WorkspaceORM]] = relationship(
        "WorkspaceORM", back_populates="project", cascade="all, delete-orphan"
    )
    runs: Mapped[list[TestRunORM]] = relationship("TestRunORM", back_populates="project", cascade="all, delete-orphan")


class RequirementORM(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    qa_model: Mapped[dict | None] = mapped_column(JsonDict, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)
    external_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="requirements")
    test_designs: Mapped[list[TestDesignORM]] = relationship(
        "TestDesignORM", back_populates="requirement", cascade="all, delete-orphan"
    )


class TestDesignORM(Base):
    __tablename__ = "test_designs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="FUNCTIONAL")
    description: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(String(100), default="Medium")
    scenario_model: Mapped[dict | None] = mapped_column(JsonDict, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    requirement: Mapped[RequirementORM] = relationship("RequirementORM", back_populates="test_designs")


class TestCaseORM(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    test_design_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_designs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    preconditions: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list[str]] = mapped_column(JsonList, default=list)
    expected_result: Mapped[str] = mapped_column(Text, default="")
    test_model: Mapped[dict | None] = mapped_column(JsonDict, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="P1")
    automation_status: Mapped[str] = mapped_column(String(50), default="MANUAL", index=True)
    tags: Mapped[list[str]] = mapped_column(JsonList, default=list)
    external_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="test_cases")
    binding: Mapped[AutomationBindingORM | None] = relationship(
        "AutomationBindingORM", back_populates="test_case", uselist=False, cascade="all, delete-orphan"
    )


class AutomationBindingORM(Base):
    __tablename__ = "automation_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    test_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), unique=True, index=True
    )
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    nodeid: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), default="playwright_python")
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    test_case: Mapped[TestCaseORM] = relationship("TestCaseORM", back_populates="binding")


class WorkspaceORM(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str] = mapped_column(String(100), default="main")
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="workspaces")


class TestRunORM(Base):
    __tablename__ = "test_runs"
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    origin_failure_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("failure_records.id", ondelete="SET NULL"), nullable=True, index=True
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    requested_by: Mapped[str] = mapped_column(String(100), default="user")
    runner_type: Mapped[str] = mapped_column(String(50), default="LOCAL", index=True)
    runner_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    external_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_build_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    queue_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    environment: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    browser: Mapped[str] = mapped_column(String(50), default="chromium")
    parallel_workers: Mapped[int] = mapped_column(Integer, default=1)
    markers: Mapped[list[str]] = mapped_column(JsonList, default=list)
    nodeids: Mapped[list[str]] = mapped_column(JsonList, default=list)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    cancelled: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    #: Console output captured from the runner, so a finished run can still show what happened.
    log_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="runs")
    executions: Mapped[list[TestExecutionORM]] = relationship(
        "TestExecutionORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    external_artifacts: Mapped[list[ExternalArtifactReferenceORM]] = relationship(
        "ExternalArtifactReferenceORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    browser_sessions: Mapped[list[BrowserSessionORM]] = relationship(
        "BrowserSessionORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class TestExecutionORM(Base):
    __tablename__ = "test_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    nodeid: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    artifact_paths: Mapped[list[str]] = mapped_column(JsonList, default=list)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    timestamp_source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    run: Mapped[TestRunORM] = relationship("TestRunORM", back_populates="executions")
    failure_record: Mapped[FailureRecordORM | None] = relationship(
        "FailureRecordORM", back_populates="execution", uselist=False, cascade="all, delete-orphan"
    )
    browser_sessions: Mapped[list[BrowserSessionORM]] = relationship("BrowserSessionORM", back_populates="execution")


class BrowserSessionORM(Base):
    """A browser page opened by a test worker, linked to its run and eventual test execution."""

    __tablename__ = "browser_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    case_execution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_executions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    worker_id: Mapped[str] = mapped_column(String(100), default="main", index=True)
    browser_session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    page_id: Mapped[str] = mapped_column(String(36), index=True)
    nodeid: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    case_name: Mapped[str] = mapped_column(String(250), default="")
    current_url: Mapped[str] = mapped_column(String(2048), default="")
    page_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    run: Mapped[TestRunORM] = relationship("TestRunORM", back_populates="browser_sessions")
    execution: Mapped[TestExecutionORM | None] = relationship("TestExecutionORM", back_populates="browser_sessions")


class BreakpointORM(Base):
    __tablename__ = "breakpoints"
    __table_args__ = (
        UniqueConstraint("workspace_id", "file_path", "line_number", "source", name="uq_breakpoint_location_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class FailureRecordORM(Base):
    __tablename__ = "failure_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_executions.id", ondelete="CASCADE"), unique=True, index=True
    )
    test_nodeid: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    test_name: Mapped[str] = mapped_column(String(250), nullable=False)
    classification: Mapped[str] = mapped_column(String(100), default="UNKNOWN", index=True)
    exception_type: Mapped[str] = mapped_column(String(200), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    stack_trace: Mapped[str] = mapped_column(Text, default="")
    failing_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dom_snapshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    console_logs: Mapped[list[str]] = mapped_column(JsonList, default=list)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_proposal: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)
    evidence_bundle: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)

    execution: Mapped[TestExecutionORM] = relationship("TestExecutionORM", back_populates="failure_record")


class LocatorHistoryORM(Base):
    __tablename__ = "locator_history"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_url: Mapped[str] = mapped_column(String(2048), default="")
    locator: Mapped[str] = mapped_column(String(1000), default="")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_count: Mapped[int] = mapped_column(Integer, default=0)
    heal_count: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class FailureAnalysisORM(Base):
    __tablename__ = "failure_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    failure_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("failure_records.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", index=True)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JsonList, default=list)
    result: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class AIInvocationORM(Base):
    __tablename__ = "ai_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", index=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    token_source: Mapped[str] = mapped_column(String(20), default="unknown")
    decision_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    decision_choice: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)


class DecisionProviderConfigORM(Base):
    __tablename__ = "decision_provider_configs"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128), default="jev-1.13.0")
    base_url: Mapped[str] = mapped_column(String(2048), default="https://api.typesafe.ai/v1/systemone")
    timeout: Mapped[float] = mapped_column(Float, default=20.0)
    minimum_confidence: Mapped[float] = mapped_column(Float, default=0.60)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class AIProviderConfigORM(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String(50), default="fake")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128), default="gpt-4o-mini")
    base_url: Mapped[str] = mapped_column(String(2048), default="https://api.openai.com/v1")
    timeout: Mapped[float] = mapped_column(Float, default=30.0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    max_request_tokens: Mapped[int] = mapped_column(Integer, default=16000)
    max_daily_requests: Mapped[int] = mapped_column(Integer, default=1000)
    max_task_calls: Mapped[int] = mapped_column(Integer, default=8)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class AIDailyBudgetORM(Base):
    __tablename__ = "ai_daily_budgets"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    reserved_requests: Mapped[int] = mapped_column(Integer, default=0)


class RunnerProfileORM(Base):
    __tablename__ = "runner_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="LOCAL", index=True)  # "LOCAL", "JENKINS"
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class ExternalArtifactReferenceORM(Base):
    __tablename__ = "external_artifact_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="ALLURE")  # ALLURE, HTML_REPORT, SCREENSHOT, TRACE, LOGS
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)

    run: Mapped[TestRunORM] = relationship("TestRunORM", back_populates="external_artifacts")


class IntegrationAuditORM(Base):
    __tablename__ = "integration_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # JIRA, TESTRAIL, GITHUB, JENKINS
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # IMPORT_REQUIREMENT, CREATE_BUG, etc.
    target_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), default="user")
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", index=True)  # SUCCESS, FAILED, DRY_RUN
    details: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)


class ReleaseORM(Base):
    __tablename__ = "releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="PLANNED", index=True)
    target_date: Mapped[str] = mapped_column(String(50), default="")
    pass_rate_threshold: Mapped[float] = mapped_column(Float, default=95.0)
    max_allowed_flaky: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    blockers: Mapped[list[str]] = mapped_column(JsonList, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


# --- Phase 11: Identity, RBAC & Security ORM Models ---
class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(50), default="QA_ENGINEER", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class TeamORM(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class TeamMemberORM(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(50), default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class ApiKeyORM(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class SecurityAuditORM(Base):
    __tablename__ = "security_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(50), default="127.0.0.1")
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)


# --- Phase 12: Distributed Execution ORM Models ---
class WorkerORM(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(50), default="127.0.0.1")
    status: Mapped[str] = mapped_column(String(50), default="ONLINE", index=True)  # ONLINE, BUSY, OFFLINE, LOST
    browsers: Mapped[list[str]] = mapped_column(JsonList, default=list)
    os: Mapped[str] = mapped_column(String(50), default="linux")
    max_concurrency: Mapped[int] = mapped_column(Integer, default=4)
    current_load: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(JsonList, default=list)
    last_heartbeat_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
    registered_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class ExecutionJobORM(Base):
    __tablename__ = "execution_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    nodeids: Mapped[list[str]] = mapped_column(JsonList, default=list)
    runner_type: Mapped[str] = mapped_column(String(50), default="LOCAL")
    browser: Mapped[str] = mapped_column(String(50), default="chromium")
    priority: Mapped[int] = mapped_column(Integer, default=10, index=True)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    assigned_worker_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class ArtifactORM(Base):
    __tablename__ = "stored_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    storage_type: Mapped[str] = mapped_column(String(50), default="LOCAL")  # LOCAL, S3
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class TaskORM(Base):
    """Durable user goal. Test runs and worker jobs remain execution resources below a task."""

    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    verification: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    replan_count: Mapped[int] = mapped_column(Integer, default=0)
    max_steps: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    max_replans: Mapped[int] = mapped_column(Integer, default=2)
    max_ai_calls: Mapped[int] = mapped_column(Integer, default=8)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    current_step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)


class TaskStepORM(Base):
    __tablename__ = "agent_task_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    dependencies: Mapped[list[str]] = mapped_column(JsonList, default=list)
    condition: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    inputs: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    evidence_ids: Mapped[list[str]] = mapped_column(JsonList, default=list)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JsonDict, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=1)
    parallelizable: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)


class TaskEvidenceORM(Base):
    __tablename__ = "agent_task_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_task_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stored_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)


class TaskArtifactORM(Base):
    __tablename__ = "agent_task_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_task_steps.id", ondelete="SET NULL"), nullable=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stored_artifacts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class TaskDecisionORM(Base):
    __tablename__ = "agent_task_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_task_steps.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    choice: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)


class TaskEventORM(Base):
    __tablename__ = "agent_task_events"
    __table_args__ = (Index("ix_task_event_step_cursor", "task_id", "step_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, index=True)
