from __future__ import annotations

import re

from project_model.task_models import TaskStepSpec, TaskType


def build_plan(task_type: TaskType) -> list[TaskStepSpec]:
    """Build a bounded DAG from registered tools; no user-provided tool names are accepted."""
    templates: dict[TaskType, list[tuple[str, str, str, tuple[str, ...], dict]]] = {
        TaskType.ANALYZE_REQUIREMENT: [
            ("analyze", "Analyze requirement and persist lifecycle evidence", "requirement.analyze", (), {}),
        ],
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
            ("browser_agent", "逐步观察页面、决策并验证浏览操作", "browser.agent", (), {}),
        ],
        TaskType.EXPLORE_PRODUCT: [
            ("explore", "运行有界的产品探索循环并持久化证据", "discovery.run", (), {}),
        ],
        TaskType.ANALYZE_DISCOVERY: [
            ("collect", "Collect the unsettled scenarios and the evidence they cite", "discovery.collect_gaps", (), {}),
            ("analyze", "Ask the model to read each unsettled scenario", "discovery.analyze_gaps", ("collect",), {}),
            ("grade", "Grade evidence sufficiency and record its source", "discovery.grade_gaps", ("analyze",), {}),
            ("finalize", "Summarise what needs a human decision", "discovery.summarize_gaps", ("grade",), {}),
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


def parse_qa_goal(goal: str, inputs: dict) -> dict:
    """Resolve a small, explicit goal grammar against the selected business context."""
    text = goal.casefold()
    only_analysis = bool(re.search(r"只分析|仅分析|只检查|only analyze|analysis only", text))
    coverage_only = bool(
        re.search(r"只检查覆盖|只看覆盖|检查(?:一下)?(?:测试)?覆盖|coverage only|only inspect coverage", text)
    )
    cases_only = bool(re.search(r"(?:生成|创建|补充).{0,8}(?:缺失)?\s*(?:case|用例)|create missing cases?", text))
    no_run = bool(
        re.search(
            r"不要.{0,4}(?:跑|运行|执行).{0,6}(?:测试|用例|回归)|不跑测试|不运行测试|without running tests?|(?:do not|don't|must not) (?:run|execute) (?:(?:the|these|this|any|all) )?tests?",
            text,
        )
    )
    no_source_changes = bool(
        re.search(
            r"不要.{0,6}(?:改|修改|写入).{0,8}(?:代码|源码|源文件)|不改代码|不修改代码|no code changes?|do not modify source",
            text,
        )
    )
    no_automation_generation = bool(
        re.search(
            r"不要.{0,6}(?:生成|创建).{0,8}(?:代码|源码|自动化|测试代码)|不生成代码|不要生成自动化|do not generate (?:code|automation)",
            text,
        )
    )
    no_browser = bool(re.search(r"不要.{0,4}(?:使用|开|启动).{0,5}浏览器|no browser|without browser", text))
    no_full_regression = bool(
        re.search(r"不要.{0,6}(?:跑|运行|执行).{0,8}(?:全量|完整|全部).{0,6}(?:回归|测试)|no full regression", text)
    )
    wants_run = bool(
        re.search(
            r"(?:跑|运行|执行)(?:完)?(?:这些|这个|该|当前|目标|本次)?(?:需求的)?(?:自动化)?(?:测试|用例|回归)|run (?:these |the )?tests?",
            text,
        )
        or re.search(r"(?:跑|运行|执行).{0,8}(?:全量|完整|全部).{0,6}(?:回归|测试)", text)
    )
    wants_repair = bool(re.search(r"修复|修好|修一下|repair|fix(?: this)? failure", text))
    wants_analysis = bool(re.search(r"分析|analy[sz]e", text))
    wants_generation = bool(re.search(r"生成|创建自动化|generate automation|create automation", text))
    regenerate_automation = bool(re.search(r"重新生成|重新创建|从头生成|regenerate|recreate", text))
    negates_full_requirement = bool(
        re.search(
            r"(?:不需要|不必|不要|别|无需|不用)(?:把|将|对)?(?:当前|这个|该|已有|现有)?(?:需求|项目)?(?:做|进行)?(?:完整(?:地)?(?:测试|测)|(?:测试|测)(?:[^，。；;,.!?]{0,4}完整|[^，。；;,.!?]{0,8}(?:已有|现有)?需求(?:[^，。；;,.!?]{0,4}完整)?))",
            text,
        )
        or re.search(
            r"(?:do not|don't|does not|doesn't|must not|need not|no need to)\s+(?:(?:fully|completely|thoroughly)\s+)?(?:test|check)(?: this| the)?(?:.{0,20}existing requirement|.{0,20}requirement(?:.{0,8}(?:fully|completely|thoroughly))?)",
            text,
        )
    )
    negates_existing_requirement = bool(
        re.search(
            r"(?:不需要|不必|不要|别|无需|不用)(?:把|将|对)?(?:当前|这个|该|已有|现有)?(?:需求|项目)?(?:测试|测)(?:.{0,6}(?:已有|现有)?需求)?",
            text,
        )
        or re.search(
            r"(?:do not|don't|does not|doesn't|must not|need not|no need to)\s+(?:(?:fully|completely|thoroughly)\s+)?(?:test|check)(?: this| the)?(?:.{0,20}existing requirement|.{0,20}requirement)",
            text,
        )
    )
    explicit_full_requirement = (
        bool(re.search(r"测试完整|完整测试|完整地测试|完整地测|test (?:this )?requirement completely", text))
        and not negates_full_requirement
    )
    existing_requirement_test = bool(
        re.search(r"(?:测试|测).{0,12}(?:已有|现有).{0,4}需求|test.{0,12}existing requirement", text)
        and not negates_existing_requirement
        and not negates_full_requirement
        and not wants_analysis
    )
    full_requirement_goal = explicit_full_requirement or existing_requirement_test

    requirement_id = str(inputs.get("requirement_id") or "").strip()
    failure_id = str(inputs.get("failure_id") or "").strip()
    test_case_id = str(inputs.get("test_case_id") or "").strip()
    if failure_id:
        target = "failure"
    elif requirement_id:
        target = "requirement"
    elif test_case_id:
        target = "case"
    else:
        target = "project"

    if target == "failure":
        mode = "failure"
        create_cases = False
        generate_automation = False
        run_tests = wants_repair and not no_run and not only_analysis
        allow_source_changes = wants_repair and not no_source_changes and not only_analysis
    elif target == "requirement":
        if coverage_only:
            mode, create_cases, generate_automation, run_tests, allow_source_changes = (
                "coverage",
                False,
                False,
                False,
                False,
            )
        elif only_analysis:
            mode, create_cases, generate_automation, run_tests, allow_source_changes = (
                "analysis",
                False,
                False,
                False,
                False,
            )
        elif cases_only:
            mode, create_cases, generate_automation, run_tests, allow_source_changes = (
                "cases",
                True,
                False,
                False,
                False,
            )
        elif full_requirement_goal:
            mode = "complete_requirement"
            create_cases = True
            generate_automation = not no_automation_generation
            run_tests = not no_run
            allow_source_changes = not no_source_changes and not no_automation_generation
        elif wants_run and not full_requirement_goal:
            mode = "run_requirement"
            create_cases = False
            generate_automation = False
            run_tests = not no_run
            allow_source_changes = False
        elif wants_analysis:
            mode, create_cases, generate_automation, run_tests, allow_source_changes = (
                "analysis",
                False,
                False,
                False,
                False,
            )
        else:
            mode, create_cases, generate_automation, run_tests, allow_source_changes = (
                "coverage",
                False,
                False,
                False,
                False,
            )
    elif target == "case":
        mode = (
            "review_case"
            if only_analysis or coverage_only
            else "create_test"
            if wants_generation
            else "run_case"
            if wants_run
            else "review_case"
        )
        create_cases = False
        generate_automation = mode == "create_test" and not no_source_changes and not only_analysis
        run_tests = (mode == "run_case" or mode == "create_test") and not no_run and not only_analysis
        allow_source_changes = mode == "create_test" and not no_source_changes and not only_analysis
    else:
        mode = "run_project" if wants_run else "review_project"
        create_cases = False
        generate_automation = False
        run_tests = mode == "run_project" and not no_run
        allow_source_changes = False

    if no_run:
        run_tests = False
    return {
        "target": target,
        "mode": mode,
        "requirement_id": requirement_id,
        "failure_id": failure_id,
        "test_case_id": test_case_id,
        "nodeids": inputs.get("nodeids", []),
        "regression_nodeids": inputs.get("regression_nodeids", []),
        "create_cases": create_cases,
        "generate_automation": generate_automation,
        "run_tests": run_tests,
        "allow_source_changes": allow_source_changes,
        "allow_browser": not no_browser,
        "read_only": only_analysis or coverage_only or no_source_changes,
        "no_run": no_run,
        "no_full_regression": no_full_regression,
        "wants_repair": wants_repair,
        "regenerate_automation": regenerate_automation,
    }


def build_qa_goal_plan(contract: dict, facts: dict) -> list[TaskStepSpec]:
    """Compose existing registered task tools from current context and explicit scope."""
    steps: list[TaskStepSpec] = []

    def add(key, name, tool, depends_on=(), *, when=None, inputs=None):
        steps.append(
            TaskStepSpec(
                key=key,
                name=name,
                tool=tool,
                depends_on=list(depends_on),
                when=when or {},
                inputs=inputs or {},
                max_retries=1,
            )
        )

    mode = contract["mode"]
    if mode == "failure":
        base = build_plan(TaskType.FIX_FAILURE)
        if not contract["allow_source_changes"] or not contract["run_tests"]:
            base = base[:4] if not contract["allow_source_changes"] else base[:5]
        elif base:
            base = [base[0], base[1], base[2], base[3]] + [
                item.model_copy(update={"when": {"output_truthy": {"step": "diagnose", "field": "repairable"}}})
                for item in base[4:]
            ]
        steps.extend(base)
        add("goal_summary", "Summarize findings, changes and verification", "goal.summary", (steps[-1].key,))
        return steps

    if mode in {"review_case", "create_test"}:
        if (
            mode == "create_test"
            and (contract.get("nodeids") or facts.get("nodeids"))
            and not contract.get("regenerate_automation")
        ):
            add("inspect", "Inspect the existing bound automation", "source.inspect")
            add("review", "Validate test structure and quality", "source.review", ("inspect",))
            if contract["run_tests"]:
                add("run", "Run the existing case automation", "tests.run_regression", ("review",))
                add("run_classify", "Classify failures from real test evidence", "failure.classify_run", ("run",))
                previous = ("run_classify",)
            else:
                previous = ("review",)
            add("goal_summary", "Summarize reused automation and results", "goal.summary", previous)
            return steps
        base = build_plan(TaskType.REVIEW_TEST if mode == "review_case" else TaskType.CREATE_TEST)
        if not contract["allow_browser"]:
            base = [
                item
                for item in base
                if item.tool not in {"browser.inspect", "browser.act", "decision.select_candidate"}
            ]
            base = [item.model_copy(update={"depends_on": []}) if item.key == "generate" else item for item in base]
            base = [
                item.model_copy(update={"depends_on": [key for key in item.depends_on if key != "browser"]})
                if item.key == "report"
                else item
                for item in base
            ]
        if mode == "create_test" and (not contract["allow_source_changes"] or not contract["run_tests"]):
            base = [item for item in base if item.key in {"inspect", "decide", "act", "generate", "validate"}]
        steps.extend(base)
        add("goal_summary", "Summarize findings, changes and verification", "goal.summary", (steps[-1].key,))
        return steps

    if mode == "review_project":
        add("review_project", "Review project tests and collect findings", "goal.review_project")
        add("goal_summary", "Summarize findings and recommended next action", "goal.summary", ("review_project",))
        return steps

    if mode == "run_case":
        nodeids = contract.get("nodeids") or facts.get("nodeids") or []
        if nodeids:
            add("resolve", "Resolve the selected case automation", "tests.resolve")
            add("run", "Run the selected case automation", "tests.run_regression", ("resolve",))
            add("run_classify", "Classify failures from real test evidence", "failure.classify_run", ("run",))
            previous = ("run_classify",)
        else:
            previous = ()
        add("goal_summary", "Summarize selected case results", "goal.summary", previous)
        return steps

    if mode == "run_project":
        if not contract["run_tests"]:
            add("goal_summary", "Summarize the no-run constraint", "goal.summary")
            return steps
        if contract.get("no_full_regression") and not (contract.get("nodeids") or facts.get("nodeids")):
            add("goal_summary", "Summarize scope constraint", "goal.summary")
            return steps
        steps.extend(build_plan(TaskType.RUN_REGRESSION))
        add("goal_summary", "Summarize test results and unresolved failures", "goal.summary", (steps[-1].key,))
        return steps

    if mode == "analysis":
        if not facts.get("analysis_ready"):
            add("analyze", "Understand the requirement and persist evidence", "requirement.analyze")
        add("goal_summary", "Summarize requirement analysis", "goal.summary", (steps[-1].key,) if steps else ())
        return steps

    if mode == "coverage":
        add("coverage", "Inspect requirement, case and automation coverage", "goal.coverage")
        add("goal_summary", "Summarize coverage findings", "goal.summary", ("coverage",))
        return steps

    previous: tuple[str, ...] = ()
    if mode in {"requirement", "complete_requirement"} and not facts.get("analysis_ready"):
        add("analyze", "Understand the requirement and persist evidence", "requirement.analyze")
        previous = ("analyze",)
    if contract["create_cases"]:
        add(
            "materialize_cases", "Create missing test cases from approved scenarios", "goal.materialize_cases", previous
        )
        previous = ("materialize_cases",)

    add("coverage", "Inspect requirement, case and automation coverage", "goal.coverage", previous)
    previous = ("coverage",)

    if mode == "cases":
        add("goal_summary", "Summarize created cases", "goal.summary", previous)
        return steps

    unbound = facts.get("unbound_case_count", 0)
    cases_may_be_created = contract["create_cases"] and (
        not facts.get("analysis_ready") or facts.get("design_count", 0) > facts.get("case_count", 0)
    )
    should_plan_generation = contract["generate_automation"] and (
        unbound > 0 or cases_may_be_created or not facts.get("case_count")
    )
    generation_condition = {"output_truthy": {"step": "coverage", "field": "unbound_case_ids"}}
    if should_plan_generation:
        add(
            "generate", "Generate automation for uncovered cases", "tests.generate", previous, when=generation_condition
        )
        add(
            "validate",
            "Validate generated test source",
            "source.validate_generated",
            ("generate",),
            when=generation_condition,
        )
        previous = ("validate",)
        if contract["allow_source_changes"] and contract["run_tests"]:
            add(
                "approval",
                "Request approval before writing source",
                "task.request_approval",
                previous,
                when=generation_condition,
            )
            add(
                "write",
                "Apply the approved automation draft",
                "source.write_generated",
                ("approval",),
                when=generation_condition,
            )
            add(
                "generated_run",
                "Run generated tests before registering cases",
                "tests.run_generated",
                ("write",),
                when=generation_condition,
            )
            add(
                "register",
                "Register passing generated tests to their cases",
                "tests.register_case",
                ("generated_run",),
                when=generation_condition,
            )
            previous = ("register",)

    if contract["run_tests"]:
        add("resolve_tests", "Resolve only tests bound to this requirement", "tests.resolve_requirement", previous)
        add(
            "run",
            "Run the selected requirement tests",
            "tests.run_regression",
            ("resolve_tests",),
            when={"output_truthy": {"step": "resolve_tests", "field": "nodeids"}},
        )
        add("run_classify", "Classify failures from real test evidence", "failure.classify_run", ("run",))
        previous = ("run_classify",)
        first_failure = {"output_truthy": {"step": "run_classify", "field": "first_failure_id"}}
        failure_specs = build_plan(TaskType.FIX_FAILURE)[:4]
        failure_keys = {item.key: f"failure_{item.key}" for item in failure_specs}
        for item in failure_specs:
            inputs = {**item.inputs}
            if item.key == "collect":
                inputs["failure_id"] = {"$output": "run_classify.first_failure_id"}
            dependencies = (
                (previous[-1],) if item.key == "collect" else tuple(failure_keys[key] for key in item.depends_on)
            )
            add(failure_keys[item.key], item.name, item.tool, dependencies, when=first_failure, inputs=inputs)
        if contract["allow_source_changes"] and contract["run_tests"]:
            repair_condition = {"output_truthy": {"step": "run_classify", "field": "repairable_failure_id"}}
            repair_specs = build_plan(TaskType.FIX_FAILURE)[4:]
            repair_keys = {item.key: f"repair_{item.key}" for item in repair_specs}
            key_map = {**failure_keys, **repair_keys}
            for item in repair_specs:
                conditions = {**item.when, **repair_condition}
                add(
                    repair_keys[item.key],
                    item.name,
                    item.tool,
                    tuple(key_map[key] for key in item.depends_on),
                    when=conditions,
                    inputs=item.inputs,
                )
        previous = (
            ("repair_verify",) if contract["allow_source_changes"] and contract["run_tests"] else ("failure_diagnose",)
        )

    add("goal_summary", "Summarize completed work, evidence and next action", "goal.summary", previous)
    return steps
