"""Re-capture UI audit routes and keyboard checks against the local Vite app."""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("AI_QA_AUDIT_URL", "http://127.0.0.1:5174")
AUDIT_DIR = Path(__file__).resolve().parent
PROJECT_ID = "proj_dee3d500c002"
ROUTES = [
    ("dashboard", "/"),
    ("projects", "/projects"),
    ("requirements", "/requirements"),
    ("test-cases", "/test-cases"),
    ("automation-studio", f"/projects/{PROJECT_ID}/studio"),
    ("runs", "/runs"),
    ("tasks", "/tasks"),
    ("recorder", "/recorder"),
    ("distributed-workers", "/workers"),
    ("flaky", "/flaky"),
    ("failures", "/failures"),
    ("quality", "/quality"),
    ("security", "/security"),
    ("settings", "/settings"),
]
VIEWPORTS = [(1440, 900), (1920, 1080)]
MOBILE_ROUTES = ["recorder", "test-cases", "distributed-workers", "runs", "settings"]


def login_if_needed(page) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded")
    password = page.locator("#login-password")
    if password.count() == 0:
        return
    email = os.environ.get("AI_QA_AUDIT_EMAIL")
    password_value = os.environ.get("AI_QA_AUDIT_PASSWORD")
    if not email or not password_value:
        raise RuntimeError("Set AI_QA_AUDIT_EMAIL and AI_QA_AUDIT_PASSWORD for the local audit user.")
    page.locator("#login-email").fill(email)
    password.fill(password_value)
    page.locator("button[type=submit]").click()
    page.locator(".app-container").wait_for(timeout=15000)


def inspect(page, name: str, route: str, viewport: tuple[int, int], errors: list[str]) -> dict:
    width, height = viewport
    page.set_viewport_size({"width": width, "height": height})
    response = page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
    page.wait_for_selector(".content-viewport", timeout=15000)
    page.wait_for_timeout(1000)
    errors_before_route = len(errors)
    metrics = page.evaluate(
        """() => {
          const luminance = (hex) => {
            const rgb = hex.replace('#', '').match(/../g).map((part) => parseInt(part, 16) / 255);
            const linear = rgb.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
          };
          const contrast = (first, second) => {
            const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
            return Number(((values[0] + 0.05) / (values[1] + 0.05)).toFixed(2));
          };
          const content = document.querySelector('.content-viewport');
          const consoles = [...document.querySelectorAll('.run-console')];
          const muted = getComputedStyle(document.documentElement).getPropertyValue('--ui-ink-muted').trim();
          return {
            contentWidth: content?.clientWidth ?? null,
            contentScrollWidth: content?.scrollWidth ?? null,
            horizontalOverflow: !!content && content.scrollWidth > content.clientWidth + 1,
            documentWidth: document.documentElement.clientWidth,
            documentScrollWidth: document.documentElement.scrollWidth,
            documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
            consoleOpen: consoles.length ? consoles.some((item) => item.open) : null,
            mutedToken: muted,
            mutedContrastOnWhite: contrast(muted, '#ffffff'),
            mutedContrastOnCanvas: contrast(muted, '#f5f7fc'),
            navNames: [...document.querySelectorAll('.nav-item')].map((item) => item.getAttribute('aria-label'))
          };
        }"""
    )
    screenshot = f"{name}-{width}x{height}.png"
    page.screenshot(path=str(AUDIT_DIR / screenshot), animations="disabled")
    return {
        "name": name,
        "route": route,
        "viewport": f"{width}x{height}",
        "http": response.status if response else None,
        **metrics,
        "newPageErrors": len(errors) - errors_before_route,
        "screenshot": screenshot,
    }


def main() -> None:
    errors: list[str] = []
    results: list[dict] = []
    interactions: dict = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        login_if_needed(page)

        for name, route in ROUTES:
            for viewport in VIEWPORTS:
                results.append(inspect(page, name, route, viewport, errors))

        for name in MOBILE_ROUTES:
            route = dict(ROUTES)[name]
            results.append(inspect(page, name, route, (390, 844), errors))

        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{BASE_URL}/runs", wait_until="domcontentloaded")
        page.wait_for_selector(".run-console-summary", timeout=10000)
        summary = page.locator(".run-console-summary").first
        summary.focus()
        page.keyboard.press("Enter")
        enter_opens = summary.evaluate("node => node.parentElement.open")
        page.keyboard.press("Space")
        space_closes = not summary.evaluate("node => node.parentElement.open")
        interactions["runs_console_keyboard_toggle"] = {
            "enter_opens": enter_opens,
            "space_closes": space_closes,
        }

        page.goto(f"{BASE_URL}/recorder", wait_until="domcontentloaded")
        browser_view = page.locator(".recorder-browser-viewport")
        browser_view.focus()
        page.keyboard.press("Shift+Escape")
        interactions["recorder_keyboard_exit"] = {
            "url_input_receives_focus": page.locator(".recorder-url-input").evaluate(
                "node => document.activeElement === node"
            ),
            "hint_visible": page.locator("#recorder-keyboard-help").is_visible(),
        }

        interactions["pageErrors"] = errors
        browser.close()

    report = {
        "results": results,
        "pageErrors": errors,
        "interactions": interactions,
        "summary": {
            "routeVisits": len(results),
            "httpFailures": sum(1 for result in results if result["http"] != 200),
            "overflowPages": sum(
                1 for result in results if result["horizontalOverflow"] or result["documentOverflow"]
            ),
        },
    }
    (AUDIT_DIR / "audit-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"] | {"interactions": interactions}, ensure_ascii=False))


if __name__ == "__main__":
    main()
