import pytest
from project_model.models import QAChatRequest
from pydantic import ValidationError


def test_qa_assistant_request_uses_nested_context_contract() -> None:
    request = QAChatRequest.model_validate(
        {
            "action": "explain",
            "message": "Explain this test",
            "context": {
                "project_id": "project-1",
                "current_file": "tests/test_login.py",
                "selected_code": "def test_login(): pass",
            },
        }
    )

    assert request.action == "explain"
    assert request.context.current_file == "tests/test_login.py"


def test_qa_assistant_rejects_the_old_flat_request_shape() -> None:
    with pytest.raises(ValidationError):
        QAChatRequest.model_validate(
            {
                "message": "Explain this test",
                "project_id": "project-1",
                "current_file": "tests/test_login.py",
                "selected_code": "def test_login(): pass",
                "context_type": "explain",
            }
        )
