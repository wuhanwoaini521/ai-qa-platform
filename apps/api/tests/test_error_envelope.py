import pytest


@pytest.mark.asyncio
async def test_http_errors_have_stable_code_and_request_correlation(client):
    response = await client.get("/api/projects/nonexistent")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "HTTP_404"
    assert body["message"] == body["detail"] == "Project not found"
    assert body["request_id"] == response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_validation_error_does_not_echo_secret_inputs(client):
    response = await client.put("/api/ai/settings", json={"api_key": "synthetic-secret", "provider": "unknown"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "synthetic-secret" not in response.text
    assert body["request_id"] == response.headers["x-request-id"]
