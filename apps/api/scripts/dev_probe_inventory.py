"""Read-only inventory of probe/demo projects created during local verification.

This script never deletes or mutates data. It is the non-destructive half of the
"dev database has probe data" problem: it lists candidate projects, their counts and the
exact size of the noise they add to dashboard statistics, so cleanup can be approved and
executed deliberately.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.persistence.database import async_session_factory
from app.persistence.models import ProjectORM, RequirementORM, TestCaseORM, TestRunORM
from sqlalchemy import func, select

PROBE_PREFIXES = (
    "AI Live Probe",
    "Grounded Assertion Demo",
    "Assertion-to-Run Slice",
    "Frozen Slice Evidence",
    "Assertion to Run (final)",
)


async def inventory(prefixes: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    async with async_session_factory() as session:
        projects = (await session.execute(select(ProjectORM).order_by(ProjectORM.created_at))).scalars().all()
        for project in projects:
            if not any(project.name.startswith(prefix) for prefix in prefixes):
                continue
            requirement_count = await session.scalar(
                select(func.count()).select_from(RequirementORM).where(RequirementORM.project_id == project.id)
            )
            case_count = await session.scalar(
                select(func.count()).select_from(TestCaseORM).where(TestCaseORM.project_id == project.id)
            )
            run_count = await session.scalar(
                select(func.count()).select_from(TestRunORM).where(TestRunORM.project_id == project.id)
            )
            rows.append(
                {
                    "project_id": project.id,
                    "name": project.name,
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "requirements": requirement_count,
                    "test_cases": case_count,
                    "runs": run_count,
                    "workspace_dir": str(Path("runtime/workspaces") / project.id),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="List probe projects without modifying data.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--prefix", action="append", default=[], help="extra project name prefix")
    args = parser.parse_args()
    prefixes = PROBE_PREFIXES + tuple(args.prefix)
    rows = asyncio.run(inventory(prefixes))
    if args.json:
        print(json.dumps({"prefixes": list(prefixes), "projects": rows}, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("No probe projects found.")
        return 0
    print(f"{len(rows)} probe project(s) — nothing was deleted.\n")
    for row in rows:
        print(
            f"- {row['name']} ({row['project_id']}) "
            f"requirements={row['requirements']} cases={row['test_cases']} runs={row['runs']}"
        )
    print("\nReview this list, then delete deliberately (for example via the project admin UI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
