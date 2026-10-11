"""Owned, idempotent demo seed. Execution history is always created by TestRunService."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from project_model.lifecycle import (
    AcceptanceCriterion,
    AnalysisRecord,
    BusinessFlowStep,
    BusinessRule,
    CoverageReferences,
    ModernTestModel,
    RequirementAnalysis,
    RequirementDocument,
    RequirementRisk,
    TestOracle,
    TestScenario,
)

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
from app.services.workspace_service import WorkspaceService

DEMO_ID = "proj_golden_shop_v1"
DEMO_KIND = "golden_shop_v1"
DEMO_REQUIREMENT = "req_golden_shop_v1"
DEMO_SOURCE = Path(__file__).resolve().parents[4] / "examples" / "demo-shop"
demo_lock = asyncio.Lock()


def demo_document() -> RequirementDocument:
    descriptions = [
        "按商品名称搜索，仅显示匹配商品；忽略大小写。",
        "打开商品详情，显示商品名称、价格与加入购物车按钮。",
        "选择颜色与尺码，加入购物车后保留所选规格。",
        "购物车显示商品、规格、数量，金额符合价格乘数量。",
        "无匹配商品时显示明确空状态，无商品卡片。",
        "重复加入相同规格时合并数量，重新计算金额。",
        "分类与最高价格条件同时生效，只显示满足全部条件的商品。",
        "购物车数量增减、归零移除时同步更新商品行和总金额。",
    ]
    criteria = [
        AcceptanceCriterion(id=f"AC-{i:03}", description=text, negative_required=i == 5)
        for i, text in enumerate(descriptions, 1)
    ]
    rules = [
        BusinessRule(
            id="BR-001",
            description="商品、颜色和尺码共同标识购物车行；相同规格合并数量。",
            criterion_ids=["AC-003", "AC-006", "AC-008"],
        ),
        BusinessRule(
            id="BR-002",
            description="行金额 = 单价 × 数量；总金额 = 行金额之和。",
            criterion_ids=["AC-004", "AC-006", "AC-008"],
        ),
        BusinessRule(
            id="BR-003", description="按商品名称进行大小写不敏感的包含匹配。", criterion_ids=["AC-001", "AC-005"]
        ),
        BusinessRule(
            id="BR-004", description="分类与最高价格筛选取交集；最高价格边界包含等于。", criterion_ids=["AC-007"]
        ),
        BusinessRule(
            id="BR-005", description="减少至零或移除商品时删除购物车行并重新计算总额。", criterion_ids=["AC-008"]
        ),
    ]
    flow = [
        BusinessFlowStep(
            id=f"FLOW-{i:03}",
            title=title,
            next_ids=[f"FLOW-{i + 1:03}"] if i < 5 else [],
            criterion_ids=[f"AC-{min(i, 4):03}"],
        )
        for i, title in enumerate(["搜索商品", "打开商品", "选择规格", "加入购物车", "验证购物车"], 1)
    ]
    risks = [
        RequirementRisk(
            id="RISK-001",
            title="购买操作不可达",
            severity="High",
            impact="加入购物车动作失败，阻断核心购买流程。",
            criterion_ids=["AC-002", "AC-004"],
            rationale="主购买路径与稳定的可访问名称直接相关。",
        ),
        RequirementRisk(
            id="RISK-002",
            title="商品规格或金额错误",
            severity="High",
            impact="购买的规格与预期不一致或收费错误。",
            criterion_ids=["AC-003", "AC-004", "AC-006", "AC-008"],
            rationale="必须检查独立业务 Oracle。",
        ),
        RequirementRisk(
            id="RISK-003",
            title="搜索空结果不可理解",
            severity="Medium",
            impact="用户无法区分无商品与加载失败。",
            criterion_ids=["AC-001", "AC-005"],
        ),
        RequirementRisk(
            id="RISK-004",
            title="过滤条件组合错误",
            severity="Medium",
            impact="用户可能看到超出所选分类或价格范围的商品。",
            criterion_ids=["AC-007"],
        ),
        RequirementRisk(
            id="RISK-005",
            title="购物车数量修改未同步金额",
            severity="High",
            impact="购物车显示的商品数量与应付金额不一致。",
            criterion_ids=["AC-008"],
        ),
    ]
    definitions = [
        (
            "搜索匹配商品",
            "确认名称搜索与大小写不敏感匹配",
            ["AC-001"],
            ["BR-003"],
            ["RISK-003"],
            ["FLOW-001"],
            "normal",
            "equivalence",
            ["打开商店", "搜索 tee"],
            ["仅显示 Everyday Tee"],
        ),
        (
            "商品详情可操作",
            "确认所选商品详情与购买入口",
            ["AC-002"],
            [],
            ["RISK-001"],
            ["FLOW-002"],
            "normal",
            "happy_path",
            ["打开 Everyday Tee"],
            ["显示商品名称和可用 Add to cart 按钮"],
        ),
        (
            "选择商品规格",
            "确认颜色与尺码的选择结果",
            ["AC-003"],
            ["BR-001"],
            ["RISK-002"],
            ["FLOW-003"],
            "alternative",
            "state_transition",
            ["打开商品", "选择 Navy 与 M"],
            ["颜色为 Navy，尺码为 M"],
        ),
        (
            "加入购物车并验证金额",
            "验证商品、规格、数量、金额的完整购买路径",
            ["AC-003", "AC-004"],
            ["BR-001", "BR-002"],
            ["RISK-001", "RISK-002"],
            ["FLOW-004", "FLOW-005"],
            "normal",
            "risk_based",
            ["选择 Navy/M", "加入购物车", "打开购物车"],
            ["Everyday Tee · Navy · M · Quantity: 1", "Total: $29.00"],
        ),
        (
            "未知搜索空状态",
            "防止无匹配搜索显示旧商品或无反馈",
            ["AC-005"],
            ["BR-003"],
            ["RISK-003"],
            ["FLOW-001"],
            "negative",
            "negative",
            ["搜索 nonexistent-qa-product"],
            ["显示 No products found，无商品卡片"],
        ),
        (
            "已知定位器变化回归",
            "保留原购物车 Oracle，演示定位器证据、审批与重跑",
            ["AC-004"],
            ["BR-002"],
            ["RISK-001"],
            ["FLOW-004", "FLOW-005"],
            "alternative",
            "error_guessing",
            ["打开商品", "点击过期 legacy-add-cart 定位器", "验证购物车"],
            ["商品与总金额保持业务预期"],
        ),
        (
            "重复加入合并数量",
            "验证相同商品规格合并和金额重算",
            ["AC-006"],
            ["BR-001", "BR-002"],
            ["RISK-002"],
            ["FLOW-004", "FLOW-005"],
            "alternative",
            "boundary",
            ["连续两次加入 Navy/M", "打开购物车"],
            ["Quantity: 2，Total: $58.00"],
        ),
        (
            "分类与价格范围过滤",
            "确认分类和最高价格同时筛选且价格边界有效",
            ["AC-007"],
            ["BR-004"],
            ["RISK-004"],
            ["FLOW-001"],
            "alternative",
            "boundary",
            ["选择 Apparel 分类", "设置最高价格为 $30", "应用过滤"],
            ["只显示 Apparel 分类且价格不高于 $30 的商品"],
        ),
        (
            "购物车数量修改与移除",
            "确认增减数量、删除商品后金额与空状态一致",
            ["AC-008"],
            ["BR-002", "BR-005"],
            ["RISK-005"],
            ["FLOW-005"],
            "alternative",
            "state_transition",
            ["加入 Everyday Tee", "增加数量", "减少数量", "移除商品"],
            ["数量和总额同步更新；移除后显示空购物车与 $0.00"],
        ),
    ]
    scenarios = [
        TestScenario(
            id=f"SCN-{i:03}",
            title=title,
            intent=intent,
            coverage=CoverageReferences(criterion_ids=ac, rule_ids=br, risk_ids=risk, flow_ids=steps),
            path_type=path,
            technique=technique,
            priority="P0" if i in (4, 6) else "P1",
            actions=actions,
            expected_outcomes=outcomes,
            rationale="人工编写的 Demo 参考场景；实际 AI/Jev 分析通过工作流另行调用。",
        )
        for i, (title, intent, ac, br, risk, steps, path, technique, actions, outcomes) in enumerate(definitions, 1)
    ]
    return RequirementDocument(
        display_id="REQ-001",
        criteria=criteria,
        rules=rules,
        constraints=["本地运行，无登录或互联网依赖", "每个测试使用独立浏览器上下文"],
        dependencies=["Chromium", "pytest", "Playwright"],
        analysis=RequirementAnalysis(
            summary="从商品筛选到购物车维护的本地购买流程。包含已知定位器失败与一项待 AI 自动化的边界场景。",
            business_flow=flow,
            actors=["购物者"],
            entities=["Product", "Variant", "CartLine", "Cart"],
            risks=risks,
            scenarios=scenarios,
            ambiguities=[],
            assumptions=["价格使用整数美元，不包含税费与运费"],
            coverage_gaps=["重复加入场景目前只有人工用例"],
        ),
        history=[
            AnalysisRecord(
                id="demo-reference-v1",
                status="REFERENCE",
                started_at=utc_now().isoformat(),
                provider="human_reference",
                model="",
                prompt_version="demo-v1",
            )
        ],
    )


class GoldenDemoService:
    def __init__(self, repository_scope: RepositoryScopeFactory) -> None:
        self.repository_scope = repository_scope

    async def seed(self, *, reset=False, project_id=DEMO_ID):
        if project_id != DEMO_ID:
            raise ValueError("Reset is restricted to the owned Golden Demo project")
        async with demo_lock:
            async with self.repository_scope() as repositories:
                repository = repositories.golden_demo
                project = await repository.get_project_for_update(DEMO_ID)
                if project and project.demo_kind != DEMO_KIND:
                    raise ValueError("Reserved demo ID belongs to an unmarked project; no changes made")
                replace_existing = project is not None
                if project and not reset:
                    return {"project_id": DEMO_ID, "created": False, "shop_url": "/api/demo-shop/index.html"}
                if reset and not project:
                    raise ValueError("Demo project does not exist")
                if await repository.has_active_run(DEMO_ID) or await repository.has_active_task(DEMO_ID):
                    raise ValueError("Demo has an active run or task; finish or cancel it before resetting")
                from app.container import recorder_service

                if any(item.project_id == DEMO_ID for item in recorder_service._sessions.values()):
                    raise ValueError("Close the demo recording browser before resetting")
                saved_requirement = await repository.get_requirement(DEMO_REQUIREMENT)
                if (
                    saved_requirement
                    and (saved_requirement.qa_model or {}).get("history", [])
                    and saved_requirement.qa_model["history"][-1]["status"] == "RUNNING"
                ):
                    raise ValueError("Requirement analysis is active; finish or cancel it before resetting")
                workspace = WorkspaceService()
                destination = workspace.get_workspace_dir(DEMO_ID)
                if destination.parent != workspace.base_dir or not destination.is_relative_to(workspace.base_dir):
                    raise ValueError("Demo workspace path escaped its storage root")
                marker = destination / ".golden-demo.json"
                if destination.exists() and (
                    not marker.is_file()
                    or json.loads(marker.read_text(encoding="utf-8")) != {"demo_kind": DEMO_KIND, "project_id": DEMO_ID}
                ):
                    raise ValueError("Workspace is not marked as owned demo data; no files changed")
                # Never recursively delete. Only the checked-in demo manifest may be overwritten.
                for source in DEMO_SOURCE.rglob("*"):
                    if not source.is_file() or any(
                        part in {"__pycache__", ".pytest_cache", "artifacts"} for part in source.parts
                    ):
                        continue
                    target = (destination / source.relative_to(DEMO_SOURCE)).resolve()
                    if not target.is_relative_to(destination):
                        raise ValueError("Demo manifest contains an unsafe path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes())
                marker.write_text(json.dumps({"demo_kind": DEMO_KIND, "project_id": DEMO_ID}), encoding="utf-8")
                project = {
                    "id": DEMO_ID,
                    "demo_kind": DEMO_KIND,
                    "name": "Northstar · Golden Demo Shop",
                    "description": "从需求、风险与场景到真实浏览器执行和定位器修复的完整 QA 生命周期。",
                    "framework_type": "playwright_python",
                }
                workspace_row = {
                    "id": f"ws_{uuid4().hex[:12]}",
                    "project_id": DEMO_ID,
                    "path": str(destination),
                    "branch": "main",
                    "status": "ACTIVE",
                }
                doc = demo_document()
                requirement_row = {
                    "id": DEMO_REQUIREMENT,
                    "project_id": DEMO_ID,
                    "title": "商品搜索、规格选择与购物车验证",
                    "description": "作为购物者，我希望搜索商品、查看详情、选择规格并加入购物车，确认商品、数量和金额正确。",
                    "acceptance_criteria": "\n".join(f"{c.id}: {c.description}" for c in doc.criteria),
                    "qa_model": doc.model_dump(mode="json"),
                    "status": "READY",
                }
                targets = [
                    "test_search",
                    "test_product_detail",
                    "test_select_variant",
                    "test_add_to_cart",
                    "test_empty_search",
                    "test_known_locator_change",
                    "test_repeated_add_merges_quantity_and_total",
                    "test_category_and_price_filters",
                    "test_cart_quantity_controls_and_remove",
                ]
                test_rows = []
                for index, scenario in enumerate(doc.analysis.scenarios, 1):
                    design_id, case_id = f"des_golden_{index:03}", f"case_golden_{index:03}"
                    design = {
                        "id": design_id,
                        "requirement_id": DEMO_REQUIREMENT,
                        "title": scenario.title,
                        "description": scenario.intent,
                        "category": "NEGATIVE" if scenario.path_type == "negative" else "FUNCTIONAL",
                        "risk": "High" if scenario.priority == "P0" else "Medium",
                        "status": "READY",
                        "scenario_model": scenario.model_dump(mode="json"),
                    }
                    model = ModernTestModel(
                        display_id=f"TC-{index:03}",
                        intent=scenario.intent,
                        scenario_id=scenario.id,
                        coverage=scenario.coverage,
                        path_type=scenario.path_type,
                        technique=scenario.technique,
                        data={
                            "query": "tee",
                            "product": "Everyday Tee",
                            "color": "Navy",
                            "size": "M",
                            "price": 29,
                            "category": "Apparel",
                            "maximum_price": 30,
                        },
                        oracles=[
                            TestOracle(kind="UI", description=outcome, criterion_ids=scenario.coverage.criterion_ids)
                            for outcome in scenario.expected_outcomes
                        ],
                        evidence=["Screenshot", "DOM", "Trace", "Network"],
                        missing=["等待人工确认并生成重复加入自动化"] if index == 7 else [],
                    )
                    case = {
                        "id": case_id,
                        "project_id": DEMO_ID,
                        "requirement_id": DEMO_REQUIREMENT,
                        "test_design_id": design_id,
                        "title": scenario.title,
                        "preconditions": "本地 shop_url fixture；独立空购物车",
                        "steps": scenario.actions,
                        "expected_result": "\n".join(scenario.expected_outcomes),
                        "priority": scenario.priority,
                        "automation_status": "AUTOMATED" if index <= 6 or index >= 8 else "MANUAL",
                        "test_model": model.model_dump(mode="json"),
                        "tags": ["golden-demo", scenario.technique],
                    }
                    binding = None
                    if index <= 6 or index >= 8:
                        file = "tests/test_known_locator.py" if index == 6 else "tests/test_shop.py"
                        binding = {
                            "id": f"bind_golden_{index:03}",
                            "test_case_id": case_id,
                            "workspace_id": DEMO_ID,
                            "file_path": file,
                            "nodeid": f"{file}::{targets[index - 1]}",
                            "framework": "playwright_python",
                            "status": "ACTIVE",
                        }
                    test_rows.append((design, case, binding))
                await repository.replace_seed(
                    project, workspace_row, requirement_row, test_rows, replace_existing=replace_existing
                )
                await repositories.commit()
                if not (destination / ".git").exists():
                    await asyncio.to_thread(workspace._initialize_git_repo, destination)
                return {"project_id": DEMO_ID, "created": True, "shop_url": "/api/demo-shop/index.html"}
