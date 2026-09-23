from __future__ import annotations

import json
from datetime import datetime, timezone

from app.persistence.database import Base
from sqlalchemy import DateTime, ForeignKey, String, Text, TypeDecorator
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
