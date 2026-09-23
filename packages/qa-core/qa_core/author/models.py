from __future__ import annotations

from pydantic import BaseModel, Field


class TestSpecification(BaseModel):
    title: str
    target_url: str = "/"
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_assertions: list[str] = Field(default_factory=list)
    recommended_page_objects: list[str] = Field(default_factory=list)


class AuthoringRequest(BaseModel):
    requirement_title: str
    requirement_description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    target_framework: str = "playwright_python"
    workspace_knowledge: dict | None = None


class AuthoringResult(BaseModel):
    suggested_file_path: str
    generated_code: str
    test_specification: TestSpecification
    explanation: str
