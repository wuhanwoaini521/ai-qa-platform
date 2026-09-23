from __future__ import annotations

from pydantic import BaseModel, Field


class PageKnowledge(BaseModel):
    name: str
    url_pattern: str = ""
    locators: dict[str, str] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)


class FlowKnowledge(BaseModel):
    name: str
    description: str = ""
    steps: list[str] = Field(default_factory=list)


class ComponentKnowledge(BaseModel):
    name: str
    selectors: dict[str, str] = Field(default_factory=dict)


class WorkspaceKnowledge(BaseModel):
    pages: list[PageKnowledge] = Field(default_factory=list)
    flows: list[FlowKnowledge] = Field(default_factory=list)
    components: list[ComponentKnowledge] = Field(default_factory=list)
    raw_markdown_docs: dict[str, str] = Field(default_factory=dict)
