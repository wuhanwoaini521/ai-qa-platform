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


def test_redact_text_preserves_host_and_path_when_url_credentials_contain_email():
    safe = SensitiveRedactor.redact_text(
        "Observed https://qa.user@example.test:secret@shop.example/account?api_key=private#checkout"
    )

    assert safe == "Observed https://shop.example/account"
    assert "qa.user@example.test" not in safe
    assert "secret" not in safe and "private" not in safe


def test_redact_text_scrubs_complete_authorization_header_values():
    safe = SensitiveRedactor.redact_text("Authorization: Bearer bearer-sentinel-123")

    assert "bearer-sentinel-123" not in safe
    assert "***REDACTED***" in safe


def test_non_http_urls_do_not_persist_embedded_content_or_local_paths():
    assert SensitiveRedactor.redact_url("data:text/html,private-page-content") == "data:"
    assert SensitiveRedactor.redact_url("file:///home/qa/private/test.html") == "file:"


def test_redact_text_scrubs_values_typed_into_form_fields():
    tree = (
        '- heading "Checkout" [level=1]\n'
        '- textbox "Card number": 4111-1111-1111-1111\n'
        '  - combobox "Size":\n'
        '    - option "express" [selected]'
    )

    safe = SensitiveRedactor.redact_text(tree)

    assert "4111-1111-1111-1111" not in safe
    assert '- textbox "Card number": {filled}' in safe
    # An empty combobox keeps its option list instead of swallowing the next line.
    assert '- combobox "Size":' in safe
    assert '- option "express" [selected]' in safe


def test_redact_text_scrubs_email_us_ssn_and_common_phone_formats():
    source = (
        "Contact alex.lee+qa@example.test, SSNs 123-45-6789, 123 45 6789, and 123.45.6789, "
        "phones (415) 555-0132, 415.555.0133, +1 415-555-0134, 4155550135 ext 42, "
        "and 415‑555‑0199."
    )

    safe = SensitiveRedactor.redact_text(source)

    assert "alex.lee+qa@example.test" not in safe
    assert all(value not in safe for value in ("123-45-6789", "123 45 6789", "123.45.6789"))
    assert "415) 555-0132" not in safe and "415.555.0133" not in safe
    assert "+1 415-555-0134" not in safe and "4155550135" not in safe
    assert "415‑555‑0199" not in safe
    assert "[REDACTED_EMAIL]" in safe
    assert "[REDACTED_SSN]" in safe
    assert "[REDACTED_PHONE]" in safe


def test_redact_value_scrubs_structured_contact_and_ssn_keys():
    safe = SensitiveRedactor.redact_value(
        {
            "email": "alex@example.test",
            "contact_email": "alex@example.test",
            "phoneNumber": "(415) 555-0132",
            "mobile_phone": "+1 415 555 0133",
            "ssn": "123-45-6789",
            "socialSecurityNumber": "987-65-4321",
            "profile": {"EmailAddress": "nested@example.test"},
        }
    )

    assert safe == {
        "email": "***REDACTED***",
        "contact_email": "***REDACTED***",
        "phoneNumber": "***REDACTED***",
        "mobile_phone": "***REDACTED***",
        "ssn": "***REDACTED***",
        "socialSecurityNumber": "***REDACTED***",
        "profile": {"EmailAddress": "***REDACTED***"},
    }


def test_redaction_placeholder_detector_recognizes_persisted_forms():
    for value in ("***REDACTED***", "[REDACTED]", "[REDACTED_EMAIL]", "[redacted_phone]"):
        assert SensitiveRedactor.contains_redaction_placeholder(value)
    assert not SensitiveRedactor.contains_redaction_placeholder("Observed results are ready")


def test_redact_text_preserves_hexadecimal_identifiers():
    identifier = "651e9917c3fe472987578ab2933fa104"

    assert SensitiveRedactor.redact_text(identifier) == identifier


def test_recorder_secret_variables_are_forwarded_explicitly(monkeypatch):
    from qa_core.execution.environment import project_subprocess_environment

    environment = project_subprocess_environment({"QA_RECORDER_SECRET_ABC123": "value", "QA_DATABASE_URL": "sqlite://"})
    assert environment["QA_RECORDER_SECRET_ABC123"] == "value"
    assert "QA_DATABASE_URL" not in environment


def test_api_secret_variables_are_forwarded_explicitly():
    from qa_core.execution.environment import project_subprocess_environment

    environment = project_subprocess_environment({"QA_API_SECRET_AUTHORIZATION": "Bearer test", "QA_OTHER_SECRET": "x"})
    assert environment["QA_API_SECRET_AUTHORIZATION"] == "Bearer test"
    assert "QA_OTHER_SECRET" not in environment
