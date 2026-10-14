from playwright.sync_api import sync_playwright

PAGE_URL = "http://127.0.0.1:8766/"


def test_checkout_order():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page()
        try:
            page.goto(PAGE_URL, wait_until="domcontentloaded")
            page.get_by_label("Email").fill("qa@example.test")
            page.get_by_role("button", name="Complete order").click(timeout=3000)
            assert page.locator("#status").inner_text() == "ORDER_COMPLETED"
        finally:
            browser.close()
