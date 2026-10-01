"""Pytest plugin source used to stream the browser that the test itself is driving.

The imported project runs in its own interpreter, so the plugin is materialised beside that run's
artifacts rather than imported into the API process.
"""

from __future__ import annotations

LIVE_BROWSER_PLUGIN_NAME = "qa_platform_live_browser_plugin"

LIVE_BROWSER_PLUGIN_SOURCE = '''"""Generated for one AI QA Platform TestRun."""

from __future__ import annotations

import json
import os
import threading
import uuid

import pytest


PLUGIN_NAME = "qa-platform-live-browser"
ENV_PATH = "QA_PLATFORM_LIVE_BROWSER_LOG"


class LiveBrowserPlugin:
    def __init__(self, path):
        self.path = path
        self.worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        self.handle = open(f"{path}.{self.worker_id}", "a", encoding="utf-8")
        self.lock = threading.Lock()
        self.active = {}

    def emit(self, event):
        event.update({"worker_id": self.worker_id})
        with self.lock:
            self.handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\\n")
            self.handle.flush()

    @staticmethod
    def _nodeid(item):
        """Keep event node IDs aligned with the workspace-relative runner output."""
        relative_path = os.path.relpath(str(item.path), os.getcwd()).replace(os.sep, "/")
        _, separator, suffix = item.nodeid.partition("::")
        return f"{relative_path}::{suffix}" if separator else relative_path

    @staticmethod
    def _find_page(item):
        for value in item.funcargs.values():
            if callable(getattr(value, "screenshot", None)) and hasattr(value, "url"):
                return value
            pages = getattr(value, "pages", None)
            if pages:
                page = pages[-1]
                if callable(getattr(page, "screenshot", None)):
                    return page
        return None

    @staticmethod
    def _page_evidence(page):
        try:
            return {
                "url": str(getattr(page, "url", ""))[:2048],
                "title": str(page.title())[:200],
                "controls": page.locator("button,a[href],input:not([type=hidden]),textarea,select,[role]").evaluate_all("""els => els.slice(0,80).map(el => {
                  const tag=el.tagName.toLowerCase(), type=(el.getAttribute('type') || '').toLowerCase();
                  const role=el.getAttribute('role') || (tag==='a'?'link':tag==='button'?'button':(['input','textarea'].includes(tag)?'textbox':tag==='select'?'combobox':null));
                  const name=(el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || el.getAttribute('title') || '').trim().replaceAll(String.fromCharCode(9),' ').replaceAll(String.fromCharCode(10),' ').replaceAll(String.fromCharCode(13),' ').slice(0,120);
                  const candidates=[];
                  if(role && name) candidates.push({kind:'role',value:role,name,exact:true});
                  const testId=el.getAttribute('data-testid'); if(testId) candidates.push({kind:'test_id',value:testId});
                  const labels=el.labels ? Array.from(el.labels).map(label=>label.innerText.trim()).filter(Boolean) : [];
                  if(labels.length) candidates.push({kind:'label',value:labels[0],exact:true});
                  const placeholder=el.getAttribute('placeholder'); if(placeholder) candidates.push({kind:'placeholder',value:placeholder,exact:true});
                  if(name && el.children.length===0) candidates.push({kind:'text',value:name,exact:true});
                  if(el.id && !Array.from(el.id).every(ch=>ch>='0'&&ch<='9') && !/[0-9a-f]{8,}/i.test(el.id)) candidates.push({kind:'id',value:el.id});
                  const css=tag+(el.getAttribute('type')?'[type="'+CSS.escape(type)+'"]':''); candidates.push({kind:'css',value:css});
                  return {tag,type,role,name,candidates,visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length),enabled:!el.disabled};
                })""")
            }
        except Exception:
            return None

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item):
        page = self._find_page(item)
        if page is None:
            yield
            return

        session_id = uuid.uuid4().hex
        page_id = uuid.uuid4().hex
        nodeid = self._nodeid(item)
        record = {"session_id": session_id, "page_id": page_id, "nodeid": nodeid, "page": page, "cdp": None}
        self.active[item.nodeid] = record
        self.emit({
            "type": "session.started", "session_id": session_id, "page_id": page_id,
            "nodeid": nodeid, "case_name": item.name, "url": getattr(page, "url", ""),
            "status": "running",
        })

        # Chromium's CDP screencast is the only supported live-frame transport in v1. It subscribes
        # to the existing test page; it never launches or navigates a second browser.
        try:
            cdp = page.context.new_cdp_session(page)
            record["cdp"] = cdp

            def on_frame(params):
                data = params.get("data")
                if data:
                    self.emit({
                        "type": "frame", "session_id": session_id, "page_id": page_id,
                        "nodeid": nodeid, "case_name": item.name,
                        "url": getattr(page, "url", ""), "status": "running", "mime_type": "image/jpeg",
                        "frame": data,
                    })
                try:
                    cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
                except Exception:
                    pass

            cdp.on("Page.screencastFrame", on_frame)
            cdp.send("Page.startScreencast", {
                "format": "jpeg", "quality": 55, "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 2,
            })
        except Exception:
            # Unsupported browser engines still report session and navigation metadata. No fake
            # image is generated and the UI can state that frame streaming is unavailable.
            record["cdp"] = None

        try:
            page.on("framenavigated", lambda _frame: self.emit({
                "type": "navigation", "session_id": session_id, "page_id": page_id,
                "nodeid": nodeid, "case_name": item.name,
                "url": getattr(page, "url", ""), "status": "running",
            }))
        except Exception:
            pass

        try:
            yield
        finally:
            if record["cdp"] is not None:
                try:
                    record["cdp"].send("Page.stopScreencast")
                    record["cdp"].detach()
                except Exception:
                    pass

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        if report.when != "call":
            return
        record = self.active.pop(item.nodeid, None)
        if record is None:
            return
        self.emit({
            "type": "session.finished", "session_id": record["session_id"],
            "page_id": record["page_id"], "nodeid": record["nodeid"], "case_name": item.name,
            "url": getattr(record["page"], "url", ""),
            "status": "passed" if report.passed else "failed" if report.failed else "closed",
            "page_evidence": self._page_evidence(record["page"]) if report.failed else None,
        })

    def close(self):
        try:
            self.handle.close()
        except Exception:
            pass


def pytest_configure(config):
    path = os.environ.get(ENV_PATH)
    if not path:
        return
    parallel = bool(getattr(config.option, "numprocesses", None))
    if parallel and not hasattr(config, "workerinput"):
        return
    config.pluginmanager.register(LiveBrowserPlugin(path), PLUGIN_NAME)


def pytest_unconfigure(config):
    plugin = config.pluginmanager.get_plugin(PLUGIN_NAME)
    if plugin is not None:
        plugin.close()
        config.pluginmanager.unregister(plugin)
'''


def write_live_browser_plugin(artifacts_dir) -> str:
    """Write a per-run plugin module and return its pytest ``-p`` name."""
    path = artifacts_dir / f"{LIVE_BROWSER_PLUGIN_NAME}.py"
    path.write_text(LIVE_BROWSER_PLUGIN_SOURCE, encoding="utf-8")
    return LIVE_BROWSER_PLUGIN_NAME
