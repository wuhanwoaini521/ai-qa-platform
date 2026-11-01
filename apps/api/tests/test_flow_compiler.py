import pytest
from app.services.flow_compiler import FlowDocument, compile_flow


def _node(node_id: str, kind: str, **overrides) -> dict:
    base = {"id": node_id, "kind": kind}
    base.update(overrides)
    return base


def test_linear_flow_compiles_through_the_recorder_generator():
    document = FlowDocument(
        test_name="checkout",
        nodes=[
            _node("n1", "navigate", url="http://127.0.0.1:8099/new"),
            _node("s1", "click", locator_kind="css", locator_value="#submit"),
            _node("s2", "assert_text", locator_kind="css", locator_value="#status", value="Saved"),
        ],
    )
    result = compile_flow(document)
    code = result["code"]
    assert result["test_name"] == "test_checkout"
    assert result["node_count"] == 3
    assert result["step_count"] == 3
    # The recorder generator turns the origin into a QA_BASE_URL default and appends the path.
    # Query strings are redacted from recorded URLs by design, so only the path survives.
    assert 'os.getenv("QA_BASE_URL", "http://127.0.0.1:8099")' in code
    assert '"/new"' in code
    assert 'page.locator("#submit").click()' in code
    assert 'expect(page.locator("#status")).to_contain_text("Saved")' in code
    compile(code, "flow.py", "exec")
    assert "qa_step_id=s1" in code


def test_condition_node_compiles_to_a_nested_branch():
    document = FlowDocument(
        test_name="branch",
        nodes=[
            _node("n1", "navigate", url="http://127.0.0.1:8099/"),
            _node(
                "c1",
                "condition",
                condition_kind="test_id",
                condition_value="offer",
                then=[_node("t1", "click", locator_kind="test_id", locator_value="accept")],
                else_nodes=[_node("e1", "click", locator_kind="test_id", locator_value="dismiss")],
            ),
        ],
    )
    code = compile_flow(document)["code"]
    compile(code, "flow.py", "exec")
    assert 'if page.get_by_test_id("offer").count() > 0:' in code
    assert "else:" in code
    assert code.index("accept") < code.index("else:") < code.index("dismiss")


def test_fill_node_reads_a_run_environment_variable():
    document = FlowDocument(
        test_name="login",
        nodes=[
            _node("n1", "navigate", url="http://127.0.0.1:8099/"),
            _node("f1", "fill", locator_kind="css", locator_value="#email", env_var="QA_DATA_EMAIL"),
        ],
    )
    code = compile_flow(document)["code"]
    compile(code, "flow.py", "exec")
    assert 'os.getenv("QA_DATA_EMAIL")' in code
    assert "Set environment variable QA_DATA_EMAIL" in code


def test_empty_branch_compiles_to_pass():
    document = FlowDocument(
        test_name="empty_branch",
        nodes=[
            _node("n1", "navigate", url="http://127.0.0.1:8099/"),
            _node("c1", "condition", condition_value="#x"),
        ],
    )
    code = compile_flow(document)["code"]
    compile(code, "flow.py", "exec")
    assert "pass" in code


@pytest.mark.parametrize(
    "nodes, message",
    [
        ([_node("s1", "click", locator_kind="css", locator_value="#a")], "start with a navigate"),
        ([_node("n1", "navigate", url=""), _node("x", "click", locator_value="#a")], "requires a url"),
        (
            [_node("n1", "navigate", url="http://a"), _node("c", "click")],
            "requires a locator",
        ),
        (
            [_node("n1", "navigate", url="http://a"), _node("f", "fill", locator_value="#e")],
            "requires a value",
        ),
        (
            [_node("n1", "navigate", url="http://a"), _node("c", "condition")],
            "requires a condition value",
        ),
        (
            [
                _node("n1", "navigate", url="http://a"),
                _node("c", "click", locator_value="#a", then=[_node("t", "click", locator_value="#b")]),
            ],
            "only condition nodes may carry branches",
        ),
        (
            [
                _node("n1", "navigate", url="http://a"),
                _node("f", "fill", locator_value="#e", value="x", env_var="QA_DATA_X"),
            ],
            "either a literal value or an environment variable",
        ),
        (
            [_node("n1", "navigate", url="http://a"), _node("w", "wait", value="999999")],
            "between 0 and 120000",
        ),
        (
            [_node("n1", "navigate", url="http://a"), _node("n1", "click", locator_value="#a")],
            "must be unique",
        ),
    ],
)
def test_invalid_flows_are_rejected(nodes, message):
    with pytest.raises(ValueError, match=message):
        FlowDocument(nodes=nodes)


def test_deep_condition_nesting_is_rejected():
    deepest = _node("leaf", "click", locator_value="#a")
    current = {"id": "c5", "kind": "condition", "condition_value": "#x", "then": [deepest]}
    for index in range(4, 0, -1):
        current = {"id": f"c{index}", "kind": "condition", "condition_value": "#x", "then": [current]}
    with pytest.raises(ValueError, match="nesting deeper"):
        FlowDocument(
            nodes=[
                _node("n1", "navigate", url="http://a"),
                current,
            ]
        )
