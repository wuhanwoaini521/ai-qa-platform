from __future__ import annotations

from project_model.task_models import TaskStepSpec, TaskType


def build_plan(task_type: TaskType) -> list[TaskStepSpec]:
    """Build a bounded DAG from registered tools; no user-provided tool names are accepted."""
    templates: dict[TaskType, list[tuple[str, str, str, tuple[str, ...], dict]]] = {
        TaskType.CREATE_TEST: [
            ("inspect", "Explore the target page", "browser.inspect", (), {"input_exists": "url"}),
            (
                "decide",
                "Select a safe observed browser candidate",
                "decision.select_candidate",
                ("inspect",),
                {"input_exists": "url"},
            ),
            ("act", "Observe one safe browser action", "browser.act", ("decide",), {"input_exists": "url"}),
            (
                "generate",
                "Generate test code from the goal and evidence",
                "tests.generate",
                ("inspect", "decide", "act"),
                {},
            ),
            ("validate", "Validate generated test source", "source.validate_generated", ("generate",), {}),
            ("approval", "Approve writing generated code", "task.request_approval", ("validate",), {}),
            ("write", "Write approved test to the workspace", "source.write_generated", ("approval",), {}),
            ("run", "Run the generated test", "tests.run_generated", ("write",), {}),
            ("review", "Review execution evidence", "tests.verify", ("run",), {}),
            ("register", "Register the verified test case", "tests.register_case", ("review",), {}),
        ],
        TaskType.FIX_FAILURE: [
            ("collect", "Collect failure and runtime evidence", "failure.collect", (), {}),
            ("classify", "Classify failure from observed evidence", "failure.classify", ("collect",), {}),
            ("inspect", "Inspect the failing source", "source.inspect_failure", ("collect",), {}),
            ("diagnose", "Diagnose cause using evidence", "failure.diagnose", ("classify", "inspect"), {}),
            ("repair", "Prepare a bounded repair proposal", "failure.prepare_repair", ("diagnose",), {}),
            ("approval", "Approve the source change", "task.request_approval", ("repair",), {}),
            ("apply", "Apply approved repair in the workspace", "source.apply_repair", ("approval",), {}),
            ("validate", "Validate changed source", "source.validate_workspace", ("apply",), {}),
            ("target_run", "Run the target test", "tests.run_target", ("validate",), {}),
            (
                "regression",
                "Run requested regression scope",
                "tests.run_regression",
                ("target_run",),
                {"input_exists": "regression_nodeids"},
            ),
            ("verify", "Verify the repaired failure", "tests.verify", ("target_run", "regression"), {}),
        ],
        TaskType.OPTIMIZE_TEST: [
            ("inspect", "Inspect test source", "source.inspect", (), {}),
            ("review", "Analyze quality and flakiness risks", "source.review", ("inspect",), {}),
            ("refactor", "Generate a grounded refactor proposal", "source.generate_refactor", ("review",), {}),
            ("validate", "Validate proposed source", "source.validate_generated", ("refactor",), {}),
            ("approval", "Approve the refactor", "task.request_approval", ("validate",), {}),
            ("apply", "Apply approved refactor", "source.write_generated", ("approval",), {}),
            ("run", "Execute the optimized test", "tests.run_target", ("apply",), {}),
            ("compare", "Compare before and after evidence", "tests.compare", ("review", "run"), {}),
        ],
        TaskType.EXPLORE_PAGE: [
            ("inspect", "Observe page, accessibility tree and controls", "browser.inspect", (), {}),
            ("decide", "Select a safe next action", "decision.select_candidate", ("inspect",), {}),
            ("act", "Execute the selected safe browser action", "browser.act", ("decide",), {}),
            ("verify", "Summarize observed behavior", "browser.verify", ("act",), {}),
        ],
        TaskType.RUN_REGRESSION: [
            ("resolve", "Resolve requested regression cases", "tests.resolve", (), {}),
            ("run", "Execute regression scope", "tests.run_regression", ("resolve",), {}),
            ("classify", "Classify failures from pytest output", "failure.classify_run", ("run",), {}),
            ("report", "Aggregate verified regression result", "tests.verify", ("classify",), {}),
        ],
        TaskType.REVIEW_TEST: [
            ("inspect", "Read selected test source", "source.inspect", (), {}),
            ("review", "Analyze assertions, waits, locators and isolation", "source.review", ("inspect",), {}),
            (
                "browser",
                "Inspect target page when a URL is provided",
                "browser.inspect",
                ("review",),
                {"input_exists": "url"},
            ),
            ("report", "Produce evidence-backed review", "source.review_report", ("review", "browser"), {}),
        ],
    }
    steps = templates[task_type]
    return [
        TaskStepSpec(
            key=key,
            name=name,
            tool=tool,
            depends_on=list(dependencies),
            when=condition,
            max_retries=1,
            parallelizable=tool in {"source.inspect", "browser.inspect"},
        )
        for key, name, tool, dependencies, condition in steps
    ]
