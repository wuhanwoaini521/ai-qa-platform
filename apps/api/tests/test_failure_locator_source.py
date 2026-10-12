from __future__ import annotations

from app.services.failure_service import FailureService


def test_internal_role_selector_maps_to_one_source_call_and_generates_reviewable_diff():
    source = 'def test_sign_in(page):\n    page.get_by_role("button", name="Continue", exact=True).click()\n'
    failed_locator = 'internal:role=button[name="Continue"s]'
    source_locator = FailureService._source_locator_for_failure(
        source,
        failed_locator,
        function_name="test_sign_in",
    )

    assert source_locator == 'page.get_by_role("button", name="Continue", exact=True)'

    updated = FailureService._patched_content(
        object.__new__(FailureService),
        source,
        "tests/test_sign_in.py",
        source_locator,
        'get_by_role("button", name="Sign in")',
        test_name="test_sign_in",
    )

    assert updated == ('def test_sign_in(page):\n    page.get_by_role("button", name="Sign in").click()\n')
    assert "Continue" not in updated


def test_internal_role_selector_requires_matching_exact_name_semantics():
    source = 'def test_sign_in(page):\n    page.get_by_role("button", name="Continue").click()\n'

    assert (
        FailureService._source_locator_for_failure(
            source,
            'internal:role=button[name="Continue"s]',
            function_name="test_sign_in",
        )
        is None
    )

    exact_source = 'def test_sign_in(page):\n    page.get_by_role("button", name="Continue", exact=True).click()\n'
    assert (
        FailureService._source_locator_for_failure(
            exact_source,
            'internal:role=button[name="Continue"i]',
            function_name="test_sign_in",
        )
        is None
    )


def test_internal_role_selector_is_not_mapped_when_source_target_is_ambiguous():
    source = (
        "def test_sign_in(page):\n"
        '    page.get_by_role("button", name="Continue", exact=True).click()\n'
        '    page.get_by_role("button", name="Continue", exact=True).hover()\n'
    )

    assert (
        FailureService._source_locator_for_failure(
            source,
            'internal:role=button[name="Continue"s]',
            function_name="test_sign_in",
        )
        is None
    )
