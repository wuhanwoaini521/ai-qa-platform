"""Deterministic recorder variable extraction and its use in generated pytest cases."""

from __future__ import annotations

from app.services.recorder_service import (
    RecorderGenerateRequest,
    RecorderLocator,
    RecorderStep,
    generate_python_case,
)
from app.services.recorder_variables import extract_variables


def _fill(value: str, *, step_id: str, description: str = "", redacted: bool = False) -> RecorderStep:
    return RecorderStep(
        id=step_id,
        action="fill",
        locator=RecorderLocator(kind="css", value="#email"),
        value=None if redacted else value,
        value_redacted=redacted,
        secret_env_var="QA_EMAIL" if redacted else None,
        description=description,
    )


def test_extracts_base_url_and_non_sensitive_fill_values() -> None:
    steps = [
        RecorderStep(action="navigate", url="http://shop.example.test/orders?page=1"),
        _fill("Alice", step_id="step-name", description="Name"),
        RecorderStep(
            id="step-qty",
            action="fill",
            locator=RecorderLocator(kind="css", value="#qty"),
            value="25",
            description="Quantity",
        ),
    ]
    variables = extract_variables(steps)
    by_name = {item.name: item for item in variables}
    assert any(item.source == "url" and item.default == "http://shop.example.test" for item in variables)
    assert any(item.source == "fill" and item.default == "Alice" for item in variables)
    assert any(item.default == "25" for item in variables)
    assert all(item.step_id for item in variables)
    assert by_name  # names are stable and non-empty


def test_redacted_values_are_never_extracted() -> None:
    steps = [
        RecorderStep(action="navigate", url="http://shop.example.test/"),
        _fill("secret-value", step_id="step-secret", redacted=True, description="Password"),
    ]
    variables = extract_variables(steps)
    assert all(item.default != "secret-value" for item in variables)
    assert all(item.source != "fill" for item in variables)


def test_duplicate_values_share_one_variable_and_count_is_bounded() -> None:
    steps = [
        RecorderStep(action="navigate", url="http://shop.example.test/"),
        _fill("same-value", step_id="step-a", description="Name"),
        _fill("same-value", step_id="step-b", description="Name again"),
    ]
    fill_variables = [item for item in extract_variables(steps) if item.source == "fill"]
    assert len(fill_variables) == 1

    many = [_fill(f"value-{index}", step_id=f"step-{index}", description=f"Field {index}") for index in range(40)]
    assert len([item for item in extract_variables(many) if item.source == "fill"]) <= 20


def test_generated_case_reads_variables_from_environment() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            test_name="submit_order",
            steps=[
                RecorderStep(action="navigate", url="http://shop.example.test/orders"),
                _fill("Alice", step_id="step-name", description="Name"),
                RecorderStep(
                    id="step-submit",
                    action="click",
                    locator=RecorderLocator(kind="role", value="button", name="Submit"),
                ),
            ],
        )
    )
    compile(source, "recorded_case.py", "exec")
    assert 'os.getenv("QA_BASE_URL", "http://shop.example.test") + "/orders"' in source
    assert 'os.getenv("QA_DATA_1_NAME", "Alice")' in source


def test_redacted_generated_case_still_uses_required_secret_env() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            test_name="login",
            steps=[
                RecorderStep(action="navigate", url="http://shop.example.test/login"),
                _fill("placeholder", step_id="step-secret", description="Password", redacted=True),
            ],
        )
    )
    compile(source, "recorded_case.py", "exec")
    assert 'os.getenv("QA_EMAIL")' in source
    assert "Set environment variable QA_EMAIL" in source


def test_sensitive_looking_values_are_not_turned_into_variables() -> None:
    steps = [
        RecorderStep(action="navigate", url="http://shop.example.test/"),
        RecorderStep(
            id="step-phone",
            action="fill",
            locator=RecorderLocator(kind="css", value="#phone"),
            value="13800138000",
            description="Phone",
        ),
    ]
    variables = extract_variables(steps)
    assert all(item.default != "13800138000" for item in variables)
