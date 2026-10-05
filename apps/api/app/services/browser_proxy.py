"""Proxy options shared by API-hosted Playwright browsers."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import unquote, urlsplit

from app.settings import settings


def browser_proxy_options() -> dict[str, str] | None:
    raw = (
        settings.browser_proxy_url
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
    )
    if not raw:
        return None
    parsed = urlsplit(raw if "://" in raw else f"http://{raw}")
    if (
        parsed.scheme not in {"http", "https", "socks5"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("BROWSER_PROXY_URL 必须是 HTTP、HTTPS 或 SOCKS5 代理地址")
    options = {"server": f"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}"}
    if parsed.username:
        options["username"] = unquote(parsed.username)
    if parsed.password:
        options["password"] = unquote(parsed.password)
    bypass = settings.browser_proxy_bypass or os.getenv("NO_PROXY") or os.getenv("no_proxy")
    if bypass:
        options["bypass"] = bypass
    return options


async def launch_chromium(playwright: Any, *, headless: bool = True, **options: Any) -> Any:
    """Use an installed system browser when the bundled Chromium cannot execute."""
    try:
        return await playwright.chromium.launch(headless=headless, **options)
    except Exception as error:
        message = str(error).lower()
        if not any(
            marker in message
            for marker in (
                "spawn eperm",
                "winerror 5",
                "permission denied",
                "access is denied",
                "executable doesn't exist",
            )
        ):
            raise

        for channel in ("msedge", "chrome"):
            try:
                return await playwright.chromium.launch(headless=headless, channel=channel, **options)
            except Exception:
                pass
        raise error
