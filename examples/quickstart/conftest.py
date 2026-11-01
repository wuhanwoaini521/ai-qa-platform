"""Browser fixtures for workspace tests.

Generated and hand-written UI tests receive a real Playwright page here, so a test never has to
fabricate the page it asserts on. Set ``AI_QA_BROWSER_CHANNEL`` (for example ``chrome``) when the
bundled headless shell is unavailable on the host. The browser is launched per test and always closed.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def page():
    channel = os.environ.get("AI_QA_BROWSER_CHANNEL") or None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=channel)
        context = browser.new_context()
        test_page = context.new_page()
        try:
            yield test_page
        finally:
            context.close()
            browser.close()
