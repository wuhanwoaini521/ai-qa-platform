from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.persistence.database import Base
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, TypeDecorator
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


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    framework_type: Mapped[str] = mapped_column(String(50), default="playwright_python")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

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
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

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
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

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
    priority: Mapped[str] = mapped_column(String(10), default="P1")
    automation_status: Mapped[str] = mapped_column(String(50), default="MANUAL", index=True)
    tags: Mapped[list[str]] = mapped_column(JsonList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    test_case: Mapped[TestCaseORM] = relationship("TestCaseORM", back_populates="binding")


class WorkspaceORM(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str] = mapped_column(String(100), default="main")
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="workspaces")


class TestRunORM(Base):
    __tablename__ = "test_runs"

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
    markers: Mapped[list[str]] = mapped_column(JsonList, default=list)
    nodeids: Mapped[list[str]] = mapped_column(JsonList, default=list)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    cancelled: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    project: Mapped[ProjectORM] = relationship("ProjectORM", back_populates="runs")
    executions: Mapped[list[TestExecutionORM]] = relationship(
        "TestExecutionORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    external_artifacts: Mapped[list[ExternalArtifactReferenceORM]] = relationship(
        "ExternalArtifactReferenceORM", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[TestRunORM] = relationship("TestRunORM", back_populates="executions")
    failure_record: Mapped[FailureRecordORM | None] = relationship(
        "FailureRecordORM", back_populates="execution", uselist=False, cascade="all, delete-orphan"
    )


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    execution: Mapped[TestExecutionORM] = relationship("TestExecutionORM", back_populates="failure_record")


class AIInvocationORM(Base):
    __tablename__ = "ai_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", index=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ExternalArtifactReferenceORM(Base):
    __tablename__ = "external_artifact_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="ALLURE")  # ALLURE, HTML_REPORT, SCREENSHOT, TRACE, LOGS
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[TestRunORM] = relationship("TestRunORM", back_populates="external_artifacts")
