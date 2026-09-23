from __future__ import annotations

import os
import re
from pathlib import Path

from qa_core.knowledge.models import (
    PageKnowledge,
    WorkspaceKnowledge,
)


class KnowledgeLoader:
    """Loads workspace domain knowledge from workspace/knowledge/*.md and page objects."""

    @classmethod
    def load_from_workspace(cls, workspace_dir: Path | str) -> WorkspaceKnowledge:
        ws_path = Path(workspace_dir).resolve()
        knowledge_dir = ws_path / "knowledge"
        pages_dir = ws_path / "pages"

        wk = WorkspaceKnowledge()

        # Load markdown files in knowledge directory
        if knowledge_dir.exists():
            for root, _, files in os.walk(knowledge_dir):
                for file in files:
                    if file.endswith(".md"):
                        p = Path(root) / file
                        try:
                            content = p.read_text(encoding="utf-8")
                            wk.raw_markdown_docs[file] = content

                            # Simple parser for locators in markdown
                            locators = {}
                            for match in re.finditer(r"- `(.*?)`:\s*`?(.*?)`?$", content, re.MULTILINE):
                                locators[match.group(1)] = match.group(2)

                            wk.pages.append(
                                PageKnowledge(
                                    name=file.replace(".md", ""),
                                    locators=locators,
                                    rules=[line.strip() for line in content.splitlines() if line.startswith("#")],
                                )
                            )
                        except Exception:
                            pass

        # Scan pages folder for Page Objects
        if pages_dir.exists():
            for root, _, files in os.walk(pages_dir):
                for file in files:
                    if file.endswith(".py") and not file.startswith("__"):
                        p = Path(root) / file
                        try:
                            code = p.read_text(encoding="utf-8")
                            locators = {}
                            for match in re.finditer(
                                r"self\.([a-zA-Z0-9_]+)\s*=\s*page\.locator\(['\"](.*?)['\"]\)", code
                            ):
                                locators[match.group(1)] = match.group(2)

                            wk.pages.append(
                                PageKnowledge(
                                    name=file.replace(".py", ""),
                                    locators=locators,
                                )
                            )
                        except Exception:
                            pass

        return wk
