from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


@dataclass
class BrowserRuntimeSession:
    id: str
    environment: dict[str, str] = field(default_factory=dict)
    storage_state: dict[str, Any] | None = None
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    browser_version: str = ""
    current_url: str = "about:blank"
    status: str = "READY"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_monotonic: float = field(default_factory=time.monotonic)
    console: list[dict[str, str]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)


class BrowserFrame(Protocol):
    async def evaluate(self, expression: str, *args: Any) -> Any: ...


class BrowserMouse(Protocol):
    async def click(self, x: float, y: float) -> None: ...

    async def dblclick(self, x: float, y: float) -> None: ...

    async def move(self, x: float, y: float) -> None: ...

    async def wheel(self, delta_x: float, delta_y: float) -> None: ...


class BrowserKeyboard(Protocol):
    async def insert_text(self, text: str) -> None: ...

    async def press(self, key: str) -> None: ...


class BrowserPage(Protocol):
    """Application-facing browser page contract; implementations stay inside runtime adapters."""

    @property
    def url(self) -> str: ...

    @property
    def frames(self) -> list[BrowserFrame]: ...

    @property
    def mouse(self) -> BrowserMouse: ...

    @property
    def keyboard(self) -> BrowserKeyboard: ...

    def locator(self, selector: str) -> Any: ...

    def get_by_role(self, role: str, **kwargs: Any) -> Any: ...

    def get_by_test_id(self, test_id: str) -> Any: ...

    def get_by_label(self, text: str, **kwargs: Any) -> Any: ...

    def get_by_placeholder(self, text: str, **kwargs: Any) -> Any: ...

    def get_by_text(self, text: str, **kwargs: Any) -> Any: ...

    async def goto(self, url: str, **kwargs: Any) -> Any: ...

    async def go_back(self, **kwargs: Any) -> Any: ...

    async def go_forward(self, **kwargs: Any) -> Any: ...

    async def reload(self, **kwargs: Any) -> Any: ...

    async def title(self) -> str: ...

    async def evaluate(self, expression: str, *args: Any) -> Any: ...

    async def screenshot(self, **kwargs: Any) -> bytes: ...

    async def wait_for_timeout(self, timeout: float) -> None: ...

    async def wait_for_load_state(self, state: str, **kwargs: Any) -> None: ...

    async def wait_for_function(self, expression: str, *args: Any, **kwargs: Any) -> Any: ...

    async def wait_for_url(self, url: Any, **kwargs: Any) -> None: ...

    def on(self, event: str, handler: Callable[..., Any]) -> None: ...

    def is_closed(self) -> bool: ...

    async def close(self) -> None: ...


@dataclass
class BrowserSnapshot:
    session_id: str
    url: str
    title: str
    accessibility_tree: str
    text: str
    controls: list[dict[str, Any]]
    screenshot: bytes | None
    console: list[dict[str, str]]
    network: list[dict[str, Any]]
    tabs: list[dict[str, Any]] = field(default_factory=list)


class BrowserRuntime(Protocol):
    async def create_session(
        self,
        *,
        storage_state: dict[str, Any] | None = None,
        viewport: dict[str, int] | None = None,
        environment: dict[str, str] | None = None,
        headless: bool = True,
        launch_options: dict[str, Any] | None = None,
        block_service_workers: bool = False,
    ) -> BrowserRuntimeSession: ...

    async def restore_session(
        self,
        storage_state: dict[str, Any],
        *,
        viewport: dict[str, int] | None = None,
        environment: dict[str, str] | None = None,
    ) -> BrowserRuntimeSession: ...

    async def get_session(self, session_id: str) -> BrowserRuntimeSession | None: ...

    async def get_page(self, session_id: str) -> BrowserPage: ...

    async def get_pages(self, session_id: str) -> list[BrowserPage]: ...

    async def select_page(self, session_id: str, index: int) -> BrowserPage: ...

    def add_page_listener(self, session_id: str, listener: Callable[[BrowserPage], None]) -> None: ...

    def remove_page_listener(self, session_id: str, listener: Callable[[BrowserPage], None]) -> None: ...

    def set_active_page(self, session_id: str, page: BrowserPage) -> None: ...

    async def add_init_script(self, session_id: str, script: str) -> None: ...

    async def storage_state(self, session_id: str) -> dict[str, Any]: ...

    def is_timeout_error(self, error: Exception) -> bool: ...

    async def close_session(self, session_id: str) -> None: ...

    async def close_all(self) -> None: ...

    async def navigate(self, session_id: str, url: str, *, timeout_ms: int = 30_000) -> int | None: ...

    async def restrict_navigation(self, session_id: str, allowed_hosts: set[str]) -> None: ...

    async def snapshot(
        self,
        session_id: str,
        *,
        include_screenshot: bool = True,
        screenshot_type: str = "png",
        screenshot_quality: int | None = None,
        full_page: bool = True,
        screenshot_timeout_ms: int = 30_000,
    ) -> BrowserSnapshot: ...

    async def collect_controls(self, session_id: str) -> list[dict[str, Any]]: ...

    async def collect_evidence(self, session_id: str) -> BrowserSnapshot: ...

    async def verify_locator(
        self, session_id: str, candidate: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, bool | None]: ...

    async def verify_page_locator(
        self, page: BrowserPage, candidate: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, bool | None]: ...

    async def execute_action(self, session_id: str, candidate: dict[str, Any], action: dict[str, Any]) -> Any: ...

    async def recover_context(self, session_id: str) -> BrowserRuntimeSession | None: ...
