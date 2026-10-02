import pytest
from qa_core.ai.context import MAX_TOTAL_CHARS, ContextSelector
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.evidence import FailureEvidenceBundle
from qa_core.healing.locator_intelligence import rank_locator_candidates


@pytest.mark.parametrize(
    "message,kind",
    [
        ("AssertionError: assert 1 == 2", "ASSERTION_FAILURE"),
        ("Locator.click: strict mode violation", "LOCATOR_ERROR"),
        ("TimeoutError: timed out", "TIMEOUT_ERROR"),
        ("HTTPStatusError: 502 Bad Gateway", "NETWORK_ERROR"),
        ("NameError: name x is not defined", "CODE_ERROR"),
        ("PermissionError: denied", "ENVIRONMENT_ERROR"),
        ("Page crashed", "PAGE_CRASH"),
        ("fixture 'page' not found", "TEST_DATA_ERROR"),
        ("Worker lost", "INFRASTRUCTURE_ERROR"),
        ("unknown issue", "UNKNOWN"),
    ],
)
def test_failure_kind_respects_current_exception(message, kind):
    assert FailureClassifier.failure_kind(message, "helper.py: locator = something") == kind


def test_rank_penalizes_duplicate_dynamic_and_unstable_history():
    ranked = rank_locator_candidates(
        [
            {"kind": "role", "value": "button", "name": "Save", "evidence": {"match_count": 4}},
            {
                "kind": "test_id",
                "value": "save",
                "evidence": {"match_count": 1, "history": {"success_count": 10, "failure_count": 0}},
            },
            {"kind": "id", "value": "generated-123456789"},
        ]
    )
    assert ranked[0]["value"] == "save"
    assert ranked[-1]["evidence"]["dynamic_attribute_risk"]
    assert next(item for item in ranked if item["kind"] == "role")["evidence"]["uniqueness"] is False
    assert rank_locator_candidates([{"kind": "role", "value": "button"}])[0]["evidence"]["uniqueness"] is None


def test_context_budget_prunes_dependencies_and_selects_fixture_and_imports(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "flows").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "tests/test_x.py").write_text("from flows.login import login\ndef test_x(page):\n    login(page)\n")
    (tmp_path / "flows/login.py").write_text("def login(page):\n    return page.title()\n")
    (tmp_path / "conftest.py").write_text("import pytest\n@pytest.fixture\ndef page():\n    return None\n")
    (tmp_path / ".venv/secret.py").write_text("NEVER_READ_THIS")
    bundle = ContextSelector().select(tmp_path, "tests/test_x.py::test_x", stack_trace="x" * 50000, query="login")
    assert {"conftest.py", "flows/login.py", "tests/test_x.py"} <= set(bundle.paths)
    assert "NEVER_READ_THIS" not in bundle.render()
    assert bundle.total_chars <= MAX_TOTAL_CHARS
    rejected = ContextSelector().select(tmp_path, "../../outside.py")
    assert all(fragment.path != "../../outside.py" for fragment in rejected.fragments)
    assert any("outside the workspace" in item for item in rejected.omitted)


def test_evidence_render_is_bounded_and_redacted():
    evidence = FailureEvidenceBundle(
        nodeid="test_x",
        failure_kind="CODE_ERROR",
        error="Authorization: Bearer secret-token",
        source_context="x" * 50000,
        missing=["screenshot"],
    )
    rendered = evidence.render(2000)
    assert len(rendered) <= 2000
    assert "secret-token" not in rendered
