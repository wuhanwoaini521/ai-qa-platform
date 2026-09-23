from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FrameworkType(str, Enum):
    PLAYWRIGHT_PYTHON = "playwright_python"
    PYTEST_API = "pytest_api"
    CUSTOM = "custom"


class RequirementStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class TestDesignCategory(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    BOUNDARY = "BOUNDARY"
    NEGATIVE = "NEGATIVE"
    ANALYTICS = "ANALYTICS"
    API = "API"
    UI = "UI"


class TestCasePriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AutomationStatus(str, Enum):
    MANUAL = "MANUAL"
    DRAFT = "DRAFT"
    AUTOMATED = "AUTOMATED"


class WorkspaceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INITIALIZING = "INITIALIZING"
    ARCHIVED = "ARCHIVED"
    ERROR = "ERROR"


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


# --- Base Model ---
class EntityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Project Models ---
class ProjectBase(EntityBase):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    repository_url: str | None = Field(default=None, max_length=500)
    default_branch: str = Field(default="main", max_length=100)
    framework_type: FrameworkType = Field(default=FrameworkType.PLAYWRIGHT_PYTHON)


class ProjectCreate(ProjectBase):
    bootstrap_workspace: bool = Field(
        default=True, description="Automatically initialize starter workspace directory structure"
    )


class ProjectUpdate(EntityBase):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    repository_url: str | None = None
    default_branch: str | None = None
    framework_type: FrameworkType | None = None


class Project(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Requirement Models ---
class RequirementBase(EntityBase):
    project_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    acceptance_criteria: str = Field(default="", max_length=5000)
    status: RequirementStatus = Field(default=RequirementStatus.DRAFT)


class RequirementCreate(RequirementBase):
    pass


class RequirementUpdate(EntityBase):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    acceptance_criteria: str | None = None
    status: RequirementStatus | None = None


class Requirement(RequirementBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Test Design Models ---
class TestDesignBase(EntityBase):
    requirement_id: str
    title: str = Field(..., min_length=1, max_length=200)
    category: TestDesignCategory = Field(default=TestDesignCategory.FUNCTIONAL)
    description: str = Field(default="", max_length=3000)
    risk: str = Field(default="Medium", max_length=100)
    status: str = Field(default="DRAFT", max_length=50)


class TestDesignCreate(TestDesignBase):
    pass


class TestDesignUpdate(EntityBase):
    title: str | None = None
    category: TestDesignCategory | None = None
    description: str | None = None
    risk: str | None = None
    status: str | None = None


class TestDesign(TestDesignBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Test Case Models ---
class TestCaseBase(EntityBase):
    project_id: str
    requirement_id: str | None = None
    test_design_id: str | None = None
    title: str = Field(..., min_length=1, max_length=250)
    preconditions: str = Field(default="", max_length=2000)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = Field(default="", max_length=2000)
    priority: TestCasePriority = Field(default=TestCasePriority.P1)
    automation_status: AutomationStatus = Field(default=AutomationStatus.MANUAL)
    tags: list[str] = Field(default_factory=list)


class TestCaseCreate(TestCaseBase):
    pass


class TestCaseUpdate(EntityBase):
    requirement_id: str | None = None
    test_design_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=250)
    preconditions: str | None = None
    steps: list[str] | None = None
    expected_result: str | None = None
    priority: TestCasePriority | None = None
    automation_status: AutomationStatus | None = None
    tags: list[str] | None = None


class TestCase(TestCaseBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Workspace Models ---
class WorkspaceBase(EntityBase):
    project_id: str
    path: str
    branch: str = "main"
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE


class WorkspaceCreate(EntityBase):
    project_id: str
    branch: str = "main"


class Workspace(WorkspaceBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- File Node Model for File Tree ---
class FileNodeType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


class FileNode(BaseModel):
    name: str
    path: str
    type: FileNodeType
    size: int | None = None
    children: list[FileNode] | None = None


class FileContentPayload(BaseModel):
    path: str
    content: str


class GitChangedFile(BaseModel):
    path: str
    status: str  # e.g., 'M', 'A', 'D', '??'
    staged: bool = False


class GitDiffResult(BaseModel):
    diff: str
    changed_files: list[GitChangedFile] = Field(default_factory=list)


# --- Dashboard Stats ---
class DashboardStats(BaseModel):
    total_projects: int = 0
    total_requirements: int = 0
    total_test_cases: int = 0
    total_runs: int = 0
    recent_projects: list[Project] = Field(default_factory=list)
    recent_requirements: list[Requirement] = Field(default_factory=list)
    recent_test_cases: list[TestCase] = Field(default_factory=list)
