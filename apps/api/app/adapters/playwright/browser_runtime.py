from __future__ import annotations

import asyncio
import importlib
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from app.adapters.playwright.locator import verify_locator
from app.adapters.playwright.proxy import browser_proxy_options, launch_chromium
from app.ports.browser_runtime import BrowserPage, BrowserRuntimeSession, BrowserSnapshot
from app.settings import get_config


def _headless_chrome_user_agent(browser_version: str) -> str:
    system_name = platform.system()
    if system_name == "Darwin":
        platform_token = "Macintosh; Intel Mac OS X 10_15_7"
    elif system_name == "Windows":
        platform_token = "Windows NT 10.0; Win64; x64"
    else:
        architecture = platform.machine().lower()
        architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(architecture, architecture or "x86_64")
        platform_token = f"X11; Linux {architecture}"
    return (
        f"Mozilla/5.0 ({platform_token}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser_version} Safari/537.36"
    )


#: Overlay used by the live discovery view: draws focus boxes on the page so plain screenshots show them.
HIGHLIGHT_SCRIPT = r"""boxes => {
  const layerId='__qaDiscoveryHighlights';
  let layer=document.getElementById(layerId);
  if(!layer){layer=document.createElement('div');layer.id=layerId;
    layer.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483647';
    document.documentElement.appendChild(layer);}
  layer.textContent='';
  for(const box of (boxes||[]).slice(0,50)){
    const mark=document.createElement('div');
    const color=box.color||'#22d3ee';
    mark.style.cssText='position:fixed;left:'+box.x+'px;top:'+box.y+'px;width:'+box.width+'px;height:'+box.height+
      'px;border:2px solid '+color+';background:'+color+'22;border-radius:4px';
    layer.appendChild(mark);
  }
  return (boxes||[]).length;
}"""


@dataclass
class _PlaywrightResources:
    browser: Any
    context: Any
    page: Any
    block_service_workers: bool = False
    allowed_hosts: set[str] | None = None


class PlaywrightBrowserRuntime:
    """Own Playwright startup, browser contexts and session health for API use cases."""

    def __init__(self, *, session_ttl_seconds: float | None = None, playwright_factory=None) -> None:
        self._session_ttl_override = session_ttl_seconds
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._sessions: dict[str, BrowserRuntimeSession] = {}
        self._resources: dict[str, _PlaywrightResources] = {}
        self._event_loop = None
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._expiry_task: asyncio.Task[None] | None = None

    @staticmethod
    def is_timeout_error(error: Exception) -> bool:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        return isinstance(error, PlaywrightTimeoutError)

    async def _start(self):
        current_loop = asyncio.get_running_loop()
        if self._event_loop is not None and self._event_loop is not current_loop:
            if self._expiry_task is not None:
                self._expiry_task.cancel()
                self._expiry_task = None
            for session in self._sessions.values():
                session.status = "CLOSED"
            self._sessions.clear()
            self._resources.clear()
            self._playwright = None
            self._lock = asyncio.Lock()
            self._lifecycle_lock = asyncio.Lock()
        self._event_loop = current_loop
        if self._playwright is None:
            factory = self._playwright_factory
            if factory is None:
                factory = importlib.import_module("playwright.async_api").async_playwright
            self._playwright = await factory().start()
        return self._playwright

    def _session_ttl_seconds(self) -> float:
        return (
            self._session_ttl_override
            if self._session_ttl_override is not None
            else get_config().browser.session_idle_timeout_seconds
        )

    def _start_expiry_task(self) -> None:
        if self._expiry_task is None:
            self._expiry_task = asyncio.create_task(self._expire_idle_sessions(), name="browser-session-expiry")

    async def _expire_idle_sessions(self) -> None:
        ttl = self._session_ttl_seconds()
        interval = max(0.01, min(ttl / 2, 30.0))
        try:
            while self._sessions:
                await asyncio.sleep(interval)
                now = time.monotonic()
                for session_id, session in list(self._sessions.items()):
                    if now - session.last_activity_monotonic > ttl:
                        if self._sessions.get(session_id) is session:
                            session.status = "EXPIRED"
                            await self.close_session(session_id)
        finally:
            if self._expiry_task is asyncio.current_task():
                self._expiry_task = None

    async def create_session(
        self,
        *,
        storage_state: dict[str, Any] | None = None,
        viewport: dict[str, int] | None = None,
        environment: dict[str, str] | None = None,
        headless: bool | None = None,
        launch_options: dict[str, Any] | None = None,
        block_service_workers: bool = False,
    ) -> BrowserRuntimeSession:
        browser_config = get_config().browser
        viewport = viewport or {"width": browser_config.viewport_width, "height": browser_config.viewport_height}
        headless = browser_config.headless if headless is None else headless
        async with self._lifecycle_lock:
            playwright = await self._start()
            try:
                proxy = browser_proxy_options()
                launch_options = {"args": list(browser_config.args), **(launch_options or {})}
                if proxy:
                    launch_options["proxy"] = proxy
                browser = await launch_chromium(playwright, headless=headless, **launch_options)
            except BaseException as setup_error:
                try:
                    await self._stop_if_idle()
                except BaseException as cleanup_error:
                    setup_error.add_note(f"Playwright cleanup failed: {cleanup_error!r}")
                raise
            try:
                context_options = {"viewport": viewport}
                context_options["locale"] = browser_config.locale
                context_options["timezone_id"] = browser_config.timezone
                if headless:
                    # Some sites reset HTTP/2 navigation when Chromium exposes HeadlessChrome.
                    context_options["user_agent"] = _headless_chrome_user_agent(browser.version)
                if block_service_workers:
                    context_options["service_workers"] = "block"
                if storage_state is not None:
                    context_options["storage_state"] = storage_state
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                page.set_default_timeout(browser_config.timeout_seconds * 1000)
                page.set_default_navigation_timeout(browser_config.navigation_timeout_seconds * 1000)
            except BaseException as setup_error:
                try:
                    await browser.close()
                except BaseException as cleanup_error:
                    setup_error.add_note(f"Browser cleanup failed: {cleanup_error!r}")
                try:
                    await self._stop_if_idle()
                except BaseException as cleanup_error:
                    setup_error.add_note(f"Playwright cleanup failed: {cleanup_error!r}")
                raise
            now = datetime.now(timezone.utc)
            session = BrowserRuntimeSession(
                id=uuid4().hex,
                environment=dict(environment or {}),
                storage_state=storage_state,
                viewport=dict(viewport),
                browser_version=browser.version,
                current_url=page.url,
                created_at=now,
                last_activity=now,
            )
            self._resources[session.id] = _PlaywrightResources(
                browser=browser,
                context=context,
                page=page,
                block_service_workers=block_service_workers,
            )
            context.on("page", lambda new_page: self.set_active_page(session.id, new_page))
            page.on("console", lambda message: self._record_console(session, message))
            page.on("requestfailed", lambda request: self._record_network(session, request, failed=True))
            page.on("response", lambda response: self._record_network(session, response, failed=False))
            async with self._lock:
                self._sessions[session.id] = session
            self._start_expiry_task()
            return session

    async def restore_session(
        self,
        storage_state: dict[str, Any],
        *,
        viewport: dict[str, int] | None = None,
        environment: dict[str, str] | None = None,
    ) -> BrowserRuntimeSession:
        return await self.create_session(storage_state=storage_state, viewport=viewport, environment=environment)

    async def get_session(self, session_id: str) -> BrowserRuntimeSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session_ttl = self._session_ttl_seconds()
        if time.monotonic() - session.last_activity_monotonic > session_ttl:
            session.status = "EXPIRED"
            await self.close_session(session_id)
            return None
        resources = self._resources.get(session_id)
        if resources is None:
            session.status = "CRASHED"
            self._sessions.pop(session_id, None)
            return None
        try:
            if not resources.browser.is_connected() or resources.page.is_closed():
                session.status = "CRASHED"
                await self.close_session(session_id)
                return None
        except Exception:
            session.status = "CRASHED"
            await self.close_session(session_id)
            return None
        session.last_activity = datetime.now(timezone.utc)
        session.last_activity_monotonic = time.monotonic()
        return session

    async def get_page(self, session_id: str) -> BrowserPage:
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError("Browser session is invalid, expired or unavailable")
        return self._resources[session_id].page

    async def get_pages(self, session_id: str) -> list[BrowserPage]:
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError("Browser session is invalid, expired or unavailable")
        return list(self._resources[session_id].context.pages)

    async def select_page(self, session_id: str, index: int) -> BrowserPage:
        pages = await self.get_pages(session_id)
        if index < 0 or index >= len(pages):
            raise IndexError("Browser page index is out of range")
        self.set_active_page(session_id, pages[index])
        return pages[index]

    def add_page_listener(self, session_id: str, listener) -> None:
        resources = self._resources.get(session_id)
        if resources is None:
            raise ValueError("Browser session is invalid, expired or unavailable")
        resources.context.on("page", listener)

    def remove_page_listener(self, session_id: str, listener) -> None:
        resources = self._resources.get(session_id)
        if resources is not None:
            resources.context.remove_listener("page", listener)

    async def storage_state(self, session_id: str) -> dict[str, Any]:
        session = await self._require_session(session_id)
        state = await self._resources[session_id].context.storage_state()
        session.storage_state = state
        session.last_activity = datetime.now(timezone.utc)
        session.last_activity_monotonic = time.monotonic()
        return state

    async def close_session(self, session_id: str) -> None:
        async with self._lifecycle_lock:
            async with self._lock:
                session = self._sessions.pop(session_id, None)
                resources = self._resources.pop(session_id, None)
            if session is not None:
                for resource in (resources.context, resources.browser) if resources else ():
                    try:
                        await resource.close()
                    except Exception:
                        pass
            await self._stop_if_idle()

    async def close_all(self) -> None:
        async with self._lifecycle_lock:
            async with self._lock:
                sessions = list(self._sessions.values())
                resources = list(self._resources.values())
                self._sessions.clear()
                self._resources.clear()
            for session in sessions:
                session.status = "CLOSED"
            for item in resources:
                for resource in (item.context, item.browser):
                    try:
                        await resource.close()
                    except Exception:
                        pass
            await self._stop_if_idle()

    async def _stop_if_idle(self) -> None:
        if self._sessions:
            return
        expiry_task, self._expiry_task = self._expiry_task, None
        if expiry_task is not None and expiry_task is not asyncio.current_task():
            expiry_task.cancel()
            await asyncio.gather(expiry_task, return_exceptions=True)
        if self._playwright is not None:
            playwright, self._playwright = self._playwright, None
            await playwright.stop()

    async def navigate(self, session_id: str, url: str, *, timeout_ms: int | None = None) -> int | None:
        url_parts = urlsplit(url)
        if url_parts.scheme not in {"http", "https"} or not url_parts.hostname:
            if url != "about:blank":
                raise ValueError("Browser navigation requires an http(s) URL or about:blank")
        session = await self._require_session(session_id)
        page = self._resources[session_id].page
        timeout_ms = timeout_ms or round(get_config().browser.navigation_timeout_seconds * 1000)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        session.current_url = page.url
        session.last_activity = datetime.now(timezone.utc)
        session.last_activity_monotonic = time.monotonic()
        return response.status if response else None

    async def restrict_navigation(self, session_id: str, allowed_hosts: set[str]) -> None:
        """Restrict HTTP and WebSocket traffic to the discovery host allowlist."""
        await self._require_session(session_id)
        allowed_hosts = {host.lower().rstrip(".") for host in allowed_hosts}
        resources = self._resources[session_id]
        resources.allowed_hosts = allowed_hosts
        await self._route_allowlist(resources.context, allowed_hosts)

    @staticmethod
    async def _route_allowlist(context: Any, allowed_hosts: set[str]) -> None:
        def allowed(url: str, schemes: set[str]) -> bool:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower().rstrip(".")
            return parts.scheme in schemes and host in allowed_hosts and not parts.username and not parts.password

        async def guard(route) -> None:
            if not allowed(route.request.url, {"http", "https"}):
                await route.abort()
                return
            await route.continue_()

        async def guard_websocket(route) -> None:
            if not allowed(route.url, {"ws", "wss"}):
                await route.close(code=1008, reason="WebSocket host is outside the discovery allowlist")
                return
            route.connect_to_server()

        await context.route("**/*", guard)
        await context.route_web_socket("**/*", guard_websocket)

    async def snapshot(
        self,
        session_id: str,
        *,
        include_screenshot: bool = True,
        screenshot_type: str = "png",
        screenshot_quality: int | None = None,
        full_page: bool = True,
        screenshot_timeout_ms: int | None = None,
    ) -> BrowserSnapshot:
        session = await self._require_session(session_id)
        screenshot_timeout_ms = screenshot_timeout_ms or round(get_config().browser.timeout_seconds * 1000)
        resources = self._resources[session_id]
        page = resources.page
        accessibility = ""
        visible_text = ""
        try:
            accessibility = await page.locator("body").aria_snapshot()
        except Exception:
            pass
        try:
            visible_text = (await page.locator("body").inner_text())[:12000]
        except Exception:
            pass
        screenshot = None
        if include_screenshot:
            screenshot_options = {
                "full_page": full_page,
                "type": screenshot_type,
                "timeout": screenshot_timeout_ms,
            }
            if screenshot_quality is not None:
                screenshot_options["quality"] = screenshot_quality
            screenshot = await page.screenshot(**screenshot_options)
        tabs = [
            {"index": index, "url": item.url, "title": await item.title(), "active": item is page}
            for index, item in enumerate(resources.context.pages)
        ]
        session.current_url = page.url
        session.last_activity = datetime.now(timezone.utc)
        return BrowserSnapshot(
            session_id=session.id,
            url=page.url,
            title=await page.title(),
            accessibility_tree=accessibility[:24000],
            text=visible_text,
            controls=await self.collect_controls(session_id),
            screenshot=screenshot,
            console=list(session.console[-100:]),
            network=list(session.network[-100:]),
            tabs=tabs,
        )

    async def collect_controls(self, session_id: str) -> list[dict[str, Any]]:
        page = await self.get_page(session_id)
        return await page.locator(
            "button,a[href],input:not([type=hidden]),textarea,select,[role=button],[role=link]"
        ).evaluate_all(r"""els => els.slice(0,100).map((el,index) => {
          const tag=el.tagName.toLowerCase(), type=(tag==='input' ? (el.getAttribute('type') || 'text') : (el.getAttribute('type') || '')).toLowerCase();
          const valueLabel=tag==='input' && ['button','submit','reset'].includes(type) ? el.value : '';
          const explicitName=el.getAttribute('aria-label') || (el.labels && el.labels[0]?.innerText) || el.getAttribute('placeholder') || el.getAttribute('name') || valueLabel || '';
          const name=(tag==='select' ? explicitName : (el.innerText || explicitName)).trim().replace(/\s+/g,' ').slice(0,120);
          const role=el.getAttribute('role') || (tag==='a'?'link':tag==='button'?'button':tag==='input'||tag==='textarea'?'textbox':tag==='select'?(el.multiple||el.size>1?'listbox':'combobox'):tag);
          const href=el.getAttribute('href');
          const testId=el.getAttribute('data-testid');
          const id=el.getAttribute('id');
          const visible=!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);
          const rect=el.getBoundingClientRect();
          const boundingBox={x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)};
          const visibleWidth=Math.max(0,Math.min(rect.right,window.innerWidth||0)-Math.max(rect.left,0));
          const visibleHeight=Math.max(0,Math.min(rect.bottom,window.innerHeight||0)-Math.max(rect.top,0));
          const area=rect.width*rect.height;
          const inViewport=visibleWidth>0&&visibleHeight>0;
          const visibleRatio=area>0?Math.round((visibleWidth*visibleHeight/area)*100)/100:0;
          const enabled=!(el.disabled || el.getAttribute('aria-disabled')==='true');
          const selectedText=tag==='select' ? (el.selectedOptions[0]?.textContent || '').trim() : '';
          const hasSelectValue=tag==='select' && !!el.value && !/^(choose|select|pick|please select|--|none|尺码|请选择)/i.test(selectedText);
          const selected=!!(el.selected || el.getAttribute('aria-checked')==='true' || el.getAttribute('aria-pressed')==='true' || hasSelectValue);
          const checked=!!(el.checked || el.getAttribute('aria-checked')==='true');
          const value=tag==='select' ? el.value : '';
          const options=tag==='select' ? Array.from(el.options).slice(0,30).map(option => ({value:option.value,enabled:!option.disabled})) : [];
          return {index,tag,type,role,name,href,test_id:testId,id,visible,enabled,selected,checked,value,options,bounding_box:boundingBox,in_viewport:inViewport,visible_ratio:visibleRatio};
        })""")

    async def capture_frame(
        self,
        session_id: str,
        *,
        image_type: str = "jpeg",
        quality: int = 55,
        timeout_ms: int = 1000,
    ) -> bytes | None:
        """Viewport-only frame for a live viewer. Never raises: a slow or busy page must not break the stream."""
        try:
            page = await self.get_page(session_id)
            return await page.screenshot(type=image_type, quality=quality, timeout=timeout_ms, full_page=False)
        except Exception:
            return None

    async def paint_highlights(self, session_id: str, boxes: list[dict[str, Any]]) -> int:
        """Draw a pointer-events-free overlay on the live page so screenshots carry the focus area."""
        try:
            page = await self.get_page(session_id)
            return int(await page.evaluate(HIGHLIGHT_SCRIPT, boxes or []))
        except Exception:
            return 0

    async def collect_evidence(self, session_id: str) -> BrowserSnapshot:
        return await self.snapshot(session_id)

    async def verify_locator(self, session_id: str, candidate: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        return await verify_locator(await self.get_page(session_id), candidate, event)

    async def verify_page_locator(
        self, page: BrowserPage, candidate: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, Any]:
        return await verify_locator(page, candidate, event)

    async def execute_action(self, session_id: str, candidate: dict[str, Any], action: dict[str, Any]) -> Any:
        page = await self.get_page(session_id)
        operation = action.get("type") or action.get("action") or "click"
        timeout_ms = int(action.get("timeout_ms", round(get_config().browser.timeout_seconds * 1000)))
        if operation == "navigate":
            return await self.navigate(session_id, str(action.get("url") or ""), timeout_ms=timeout_ms)
        if operation == "back":
            result = await page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
            session = await self._require_session(session_id)
            session.current_url = page.url
            return result.status if result else None
        if operation == "scroll":
            direction = str(action.get("value") or "down").lower()
            if direction not in {"up", "down"}:
                raise ValueError("Scroll direction must be 'up' or 'down'")
            return await page.mouse.wheel(0, 650 if direction == "down" else -650)
        if operation == "wait":
            duration_ms = max(100, min(5_000, int(action.get("value") or 700)))
            await page.wait_for_timeout(duration_ms)
            return None
        kind, value = candidate.get("kind"), str(candidate.get("value") or "")
        if kind == "role":
            target = page.get_by_role(value, name=candidate.get("name"), exact=candidate.get("exact", True))
        elif kind == "test_id":
            target = page.get_by_test_id(value)
        elif kind == "label":
            target = page.get_by_label(value, exact=candidate.get("exact", True))
        elif kind == "placeholder":
            target = page.get_by_placeholder(value, exact=candidate.get("exact", True))
        elif kind == "text":
            target = page.get_by_text(value, exact=candidate.get("exact", True))
        else:
            target = page.locator(value if kind != "xpath" or value.startswith("xpath=") else f"xpath={value}")
        if candidate.get("nth") is not None:
            target = target.nth(candidate["nth"])
        if operation == "fill":
            return await target.fill(str(action.get("value") or ""), timeout=timeout_ms)
        if operation == "press":
            return await target.press(str(action.get("value") or "Enter"), timeout=timeout_ms)
        if operation == "check":
            return await target.check(timeout=timeout_ms)
        if operation == "uncheck":
            return await target.uncheck(timeout=timeout_ms)
        if operation == "select":
            return await target.select_option(action.get("value"), timeout=timeout_ms)
        if operation == "hover":
            return await target.hover(timeout=timeout_ms)
        if operation == "double_click":
            return await target.dblclick(timeout=timeout_ms)
        return await target.click(timeout=timeout_ms)

    def set_active_page(self, session_id: str, page: BrowserPage) -> None:
        session = self._sessions.get(session_id)
        resources = self._resources.get(session_id)
        if session is not None and resources is not None:
            resources.page = page
            session.current_url = page.url
            page.on("console", lambda message: self._record_console(session, message))
            page.on("requestfailed", lambda request: self._record_network(session, request, failed=True))
            page.on("response", lambda response: self._record_network(session, response, failed=False))

    async def add_init_script(self, session_id: str, script: str) -> None:
        session = await self._require_session(session_id)
        await self._resources[session.id].context.add_init_script(script)

    async def recover_context(self, session_id: str) -> BrowserRuntimeSession | None:
        session = self._sessions.get(session_id)
        resources = self._resources.get(session_id)
        if session is None or resources is None:
            return None
        try:
            if not resources.browser.is_connected():
                session.status = "CRASHED"
                return None
            current_url = session.current_url
            try:
                session.storage_state = await resources.context.storage_state()
            except Exception:
                pass
            try:
                await resources.context.close()
            except Exception:
                pass
            options = {"viewport": session.viewport}
            if resources.block_service_workers:
                options["service_workers"] = "block"
            if session.storage_state is not None:
                options["storage_state"] = session.storage_state
            resources.context = await resources.browser.new_context(**options)
            resources.page = await resources.context.new_page()
            if resources.allowed_hosts is not None:
                await self._route_allowlist(resources.context, resources.allowed_hosts)
            session.status = "READY"
            session.current_url = "about:blank"
            session.last_activity = datetime.now(timezone.utc)
            session.last_activity_monotonic = time.monotonic()
            resources.context.on("page", lambda page: self.set_active_page(session.id, page))
            self.set_active_page(session.id, resources.page)
            if current_url and current_url != "about:blank":
                await self.navigate(session.id, current_url)
            return session
        except Exception:
            session.status = "CRASHED"
            return None

    async def _require_session(self, session_id: str) -> BrowserRuntimeSession:
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError("Browser session is invalid, expired or unavailable")
        return session

    @staticmethod
    def _record_console(session: BrowserRuntimeSession, message: Any) -> None:
        if getattr(message, "type", "") == "error":
            session.console.append({"type": "error", "text": str(getattr(message, "text", ""))[:1000]})

    @staticmethod
    def _record_network(session: BrowserRuntimeSession, request_or_response: Any, *, failed: bool) -> None:
        request = getattr(request_or_response, "request", request_or_response)
        session.network.append(
            {
                "url": str(getattr(request, "url", ""))[:2000],
                "method": str(getattr(request, "method", "GET"))[:20],
                "failed": failed,
                "status": getattr(request_or_response, "status", None),
            }
        )


browser_runtime = PlaywrightBrowserRuntime()
