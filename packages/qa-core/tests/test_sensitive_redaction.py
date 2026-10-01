from qa_core.failure.redactor import SensitiveRedactor


def test_redact_url_removes_userinfo_query_and_fragment():
    safe = SensitiveRedactor.redact_url(
        "https://qa-user:qa-password@example.test/account?access_token=sentinel&email=user@example.test#private"
    )

    assert safe == "https://example.test/account"
    assert "sentinel" not in safe
    assert "qa-password" not in safe
    assert "user@example.test" not in safe


def test_redact_text_scrubs_urls_embedded_in_logs():
    safe = SensitiveRedactor.redact_text(
        "Navigated to https://example.test/path?signature=sentinel#private and continued."
    )

    assert safe == "Navigated to https://example.test/path and continued."
    assert "sentinel" not in safe


def test_redact_text_scrubs_complete_authorization_header_values():
    safe = SensitiveRedactor.redact_text("Authorization: Bearer bearer-sentinel-123")

    assert "bearer-sentinel-123" not in safe
    assert "***REDACTED***" in safe


def test_non_http_urls_do_not_persist_embedded_content_or_local_paths():
    assert SensitiveRedactor.redact_url("data:text/html,private-page-content") == "data:"
    assert SensitiveRedactor.redact_url("file:///home/qa/private/test.html") == "file:"
