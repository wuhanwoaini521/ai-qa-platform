#!/usr/bin/env python3
"""为一次交付任务创建 .ai-runs/<date>-<slug>/ 执行记录目录。

    python scripts/init_run_log.py --task-type ui-redesign --title "history redesign"
    python scripts/init_run_log.py --task-type bug-fix --title "pagination bug" --scale small
    python scripts/init_run_log.py --task-type refactor --title "billing module" --dry-run

脚本只做确定性的文件系统准备：不写业务分析内容，不覆盖既有 run。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

#: 允许的任务类型，与 SKILL.md 的路由表保持一致。
TASK_TYPES = (
    "bug-fix",
    "new-feature",
    "ui-feature",
    "ui-redesign",
    "refactor",
    "maintenance",
)

#: 完整阶段集的日志文件。
FULL_STAGES = (
    "00-request.md",
    "01-analysis.md",
    "02-plan.md",
    "03-implementation.md",
    "04-functional-test.md",
    "05-ui-review.md",
    "06-code-review.md",
    "07-fixes.md",
    "08-regression.md",
    "09-final-report.md",
)

#: UI review 只对 UI 任务有意义；纯后端任务不生成它。
UI_REVIEW_STAGE = "05-ui-review.md"
UI_TASK_TYPES = frozenset({"ui-feature", "ui-redesign"})

#: 小任务只需要请求、分析与结论。
SMALL_STAGES = ("00-request.md", "01-analysis.md", "09-final-report.md")

SCALES = ("small", "standard")
SINGLE_FILE_NAME = "run.md"
DEFAULT_RUNS_DIR = ".ai-runs"
SLUG_MAX_LENGTH = 48
DATE_FORMAT = "%Y-%m-%d"


class RunLogError(Exception):
    """用户能直接看懂的失败原因。"""


def slugify(title: str) -> str:
    """把任务标题转成目录名片段：小写、非字母数字折叠为单个连字符。"""
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug[:SLUG_MAX_LENGTH].strip("-")


def stages_for(task_type: str, scale: str, single_file: bool) -> tuple[str, ...]:
    """返回该任务类型需要生成的日志文件。"""
    if single_file:
        return (SINGLE_FILE_NAME,)
    if scale == "small":
        return SMALL_STAGES
    if task_type in UI_TASK_TYPES:
        return FULL_STAGES
    return tuple(name for name in FULL_STAGES if name != UI_REVIEW_STAGE)


def resolve_run_dir(runs_dir: Path, day: str, slug: str) -> Path:
    """同一天同名任务追加 -2、-3，绝不覆盖既有 run。"""
    base = runs_dir / f"{day}-{slug}"
    if not base.exists():
        return base
    index = 2
    while (runs_dir / f"{day}-{slug}-{index}").exists():
        index += 1
    return runs_dir / f"{day}-{slug}-{index}"


def _header(title: str, task_type: str, scale: str, day: str) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- run-date: {day}",
            f"- task-type: {task_type}",
            f"- scale: {scale}",
            "",
        ]
    )


def _stage_body(name: str, title: str, task_type: str, scale: str, day: str) -> str:
    header = _header(title, task_type, scale, day)
    if name == "00-request.md":
        return header + "\n".join(
            [
                "## Original Request",
                "",
                "## Resolved Scope",
                "",
                "## Repository / Branch / Initial Git Status",
                "",
            ]
        )
    return header


def create_run_log(
    task_type: str,
    title: str,
    runs_dir: Path,
    day: str | None = None,
    scale: str = "standard",
    single_file: bool = False,
    dry_run: bool = False,
) -> Path:
    """创建 run 目录与日志骨架，返回目录路径。dry_run 时不写任何文件。"""
    if task_type not in TASK_TYPES:
        raise RunLogError(
            f"invalid task type: {task_type!r}\nallowed:\n"
            + "".join(f"- {value}\n" for value in TASK_TYPES)
        )
    if scale not in SCALES:
        raise RunLogError(f"invalid scale: {scale!r}\nallowed: {', '.join(SCALES)}")

    if day is None:
        day = datetime.now().strftime(DATE_FORMAT)
    else:
        try:
            datetime.strptime(day, DATE_FORMAT)
        except ValueError as exc:
            raise RunLogError(f"invalid date: {day!r} (expected YYYY-MM-DD)") from exc

    slug = slugify(title) or task_type
    run_dir = resolve_run_dir(runs_dir, day, slug)
    stages = stages_for(task_type, scale, single_file)

    if dry_run:
        return run_dir

    run_dir.mkdir(parents=True)
    for name in stages:
        (run_dir / name).write_text(
            _stage_body(name, title or slug, task_type, scale, day),
            encoding="utf-8",
            newline="\n",
        )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a .ai-runs execution log directory for one delivery task."
    )
    parser.add_argument(
        "--task-type", required=True, help="task routing type: " + ", ".join(TASK_TYPES)
    )
    parser.add_argument("--title", default="", help="task title, used for the directory slug")
    parser.add_argument(
        "--runs-dir",
        default=DEFAULT_RUNS_DIR,
        help=f"root directory for run logs (default: {DEFAULT_RUNS_DIR})",
    )
    parser.add_argument("--scale", default="standard", help="one of: " + ", ".join(SCALES))
    parser.add_argument("--single-file", action="store_true", help=f"write only {SINGLE_FILE_NAME}")
    parser.add_argument("--date", help="override run date (YYYY-MM-DD); used by tests")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without writing files")
    args = parser.parse_args(argv)

    try:
        run_dir = create_run_log(
            task_type=args.task_type,
            title=args.title,
            runs_dir=Path(args.runs_dir),
            day=args.date,
            scale=args.scale,
            single_file=args.single_file,
            dry_run=args.dry_run,
        )
    except RunLogError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{'would create' if args.dry_run else 'created'} {run_dir.as_posix()}")
    if args.dry_run:
        print("dry run: nothing was written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
