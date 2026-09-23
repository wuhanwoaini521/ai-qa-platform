from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.workspace_repo import WorkspaceRepository

__all__ = [
    "ProjectRepository",
    "RequirementRepository",
    "TestDesignRepository",
    "TestCaseRepository",
    "WorkspaceRepository",
]
