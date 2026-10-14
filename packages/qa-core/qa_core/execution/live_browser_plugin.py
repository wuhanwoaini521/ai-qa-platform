"""Pytest plugin source used to stream the browser that the test itself is driving.

The imported project runs in its own interpreter, so the plugin is materialised beside that run's
artifacts rather than imported into the API process.
"""

from __future__ import annotations

LIVE_BROWSER_PLUGIN_NAME = "qa_platform_live_browser_plugin"

LIVE_BROWSER_PLUGIN_SOURCE = '''"""Generated for one AI QA Platform TestRun."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import linecache
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest
from qa_platform_sensitive_redactor import SensitiveRedactor


PLUGIN_NAME = "qa-platform-live-browser"
ENV_PATH = "QA_PLATFORM_LIVE_BROWSER_LOG"


class LiveBrowserPlugin:
    def __init__(self, path):
        self.path = path
        self.worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        self.capture_screenshot = os.environ.get("QA_CAPTURE_SCREENSHOT", "1") == "1"
        self.capture_dom = os.environ.get("QA_CAPTURE_DOM", "1") == "1"
        self.capture_console = os.environ.get("QA_CAPTURE_CONSOLE", "1") == "1"
        self.capture_network = os.environ.get("QA_CAPTURE_NETWORK", "1") == "1"
        self.max_console_entries = max(0, int(os.environ.get("QA_EVIDENCE_MAX_CONSOLE_ENTRIES", "30")))
        self.max_network_entries = max(0, int(os.environ.get("QA_EVIDENCE_MAX_NETWORK_ENTRIES", "30")))
        self.max_dom_chars = max(0, int(os.environ.get("QA_EVIDENCE_MAX_DOM_CHARS", "14000")))
        self.handle = open(f"{path}.{self.worker_id}", "a", encoding="utf-8")
        self.lock = threading.Lock()
        self.active = {}
        self.locator_originals = {}

    @staticmethod
    def _redact_text(value):
        text = SensitiveRedactor.redact_text(str(value or ""))
        text = re.sub(r"(?i)\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b", "[REDACTED_EMAIL]", text)
        return re.sub(r"(?<!\\d)(?:\\+?\\d[\\d .()/-]{7,}\\d)(?!\\d)", "[REDACTED_PHONE]", text)

    @classmethod
    def _safe_value(cls, value):
        if isinstance(value, dict):
            return {str(key): "[REDACTED]" if re.search("password|passwd|secret|token|authorization|cookie|api.?key|email|phone|address|card", str(key), re.I) else cls._safe_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._safe_value(item) for item in value]
        if isinstance(value, str):
            return cls._redact_text(value)
        return value

    @classmethod
    def _element_fingerprint(cls, locator):
        try:
            if locator.count() != 1:
                return None
            attributes = locator.evaluate("""el => ({tag:el.tagName.toLowerCase(),role:el.getAttribute('role')||'',type:(el.getAttribute('type')||'').toLowerCase(),test_id:el.getAttribute('data-testid')||'',id:el.id||'',name:el.getAttribute('name')||'',aria_label:el.getAttribute('aria-label')||'',text:(el.innerText||el.textContent||'').replace(/\\\\s+/g,' ').trim()})""")
            stable = {key: str(value) for key, value in attributes.items() if key not in {"tag", "role", "type"}}
            return {
                "sha256": hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                "tag": str(attributes.get("tag") or "")[:40],
                "role": str(attributes.get("role") or "")[:40],
                "type": str(attributes.get("type") or "")[:40],
            }
        except Exception:
            return None

    def _failure_snapshot(self, record):
        page = record["page"]
        gaps = []
        url = SensitiveRedactor.redact_url(str(getattr(page, "url", "")))
        locator = self._redact_text(record.get("failed_locator") or "") or None
        prior = record.get("successful_baselines", {}).get(record.get("failed_locator", ""))
        baseline = (
            {"status": "CAPTURED", "fingerprint": prior, "reason": None}
            if prior
            else {"status": "MISSING", "fingerprint": None, "reason": "no_prior_successful_matching_locator"}
        )
        snapshot_text_limit = min(20_000, self.max_dom_chars)
        accessibility = ""
        try:
            accessibility = page.locator("body").aria_snapshot()
        except Exception:
            gaps.append("accessibility_tree_unavailable")
        try:
            private_values = page.locator("input,textarea,select").evaluate_all(
                "els => els.map(el => el.value || '').filter(value => value.length >= 2)"
            )
            for value in private_values:
                accessibility = accessibility.replace(str(value), "[REDACTED]")
        except Exception:
            pass
        accessibility = self._redact_text(accessibility)[:snapshot_text_limit]

        dom = ""
        if self.capture_dom:
            try:
                dom = page.locator("html").evaluate("""root => {
                    const clone=root.cloneNode(true);
                    for(const el of clone.querySelectorAll('input,textarea,select')) {
                      if(el.hasAttribute('value')) el.setAttribute('value','[REDACTED]');
                      if(el.tagName==='TEXTAREA') el.textContent='[REDACTED]';
                      if(el.tagName==='SELECT') el.selectedIndex=-1;
                    }
                    for(const el of clone.querySelectorAll('*')) for(const attr of Array.from(el.attributes)) {
                      if(/password|passwd|secret|token|authorization|cookie|api.?key/i.test(attr.name)) el.setAttribute(attr.name,'[REDACTED]');
                    }
                    return clone.outerHTML;
                }""")
            except Exception:
                gaps.append("redacted_dom_unavailable")
        else:
            gaps.append("dom_capture_disabled")
        dom = self._redact_text(dom)[:snapshot_text_limit]
        if not url:
            gaps.append("url_unavailable")
        if not locator:
            gaps.append("failed_locator_unavailable")

        storage_state_status = "UNAVAILABLE"
        storage_state_ciphertext = None
        try:
            state = page.context.storage_state()
            raw_state = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            key = os.environ.get("QA_FAILURE_SNAPSHOT_ENCRYPTION_KEY", "")
            if not key:
                gaps.append("storage_state_encryption_key_unavailable")
            elif len(raw_state.encode("utf-8")) > 2_000_000:
                gaps.append("storage_state_exceeds_size_limit")
            else:
                from cryptography.fernet import Fernet

                ciphertext = Fernet(key.encode("ascii")).encrypt(raw_state.encode("utf-8")).decode("ascii")
                storage_state_ciphertext = "ephemeral:v1:" + ciphertext
                storage_state_status = "AVAILABLE"
        except ImportError:
            gaps.append("storage_state_encryption_unavailable")
        except Exception:
            gaps.append("storage_state_capture_failed")

        side_effect_steps = [
            f"{step.get('action', 'action')}:{step.get('locator', '')}"[:300]
            for step in record.get("recent_steps", [])
            if step.get("action") in {"click", "dblclick", "fill", "select_option", "check", "uncheck", "press", "hover"}
        ]
        return {
            "status": "CAPTURED" if url and (accessibility or dom) else "PARTIAL",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "failed_step_id": record.get("failed_step_id"),
            "failed_evidence_id": record.get("failed_evidence_id"),
            "url": url,
            "accessibility_tree": accessibility,
            "redacted_dom": dom,
            "failed_locator": locator,
            "original_element_baseline": baseline,
            "storage_state_status": storage_state_status,
            "storage_state_ciphertext": storage_state_ciphertext,
            "replay": {
                "status": "NOT_STARTED",
                "safe_point": "captured_storage_state_and_url" if storage_state_status == "AVAILABLE" else "captured_url_only",
                "replayed_steps": [],
                "not_replayed_steps": side_effect_steps,
                "message": "No browser actions are automatically replayed; only the captured storage state and URL may be restored.",
            },
            "evidence_gaps": gaps,
        }

    def emit(self, event):
        event.setdefault('timestamp',datetime.now(timezone.utc).isoformat())
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
    def _recorder_lineage(filename, line_number):
        lines = linecache.getlines(filename)
        for source_line in reversed(lines[max(0, line_number - 8):line_number]):
            match = re.search(r"qa_step_id=([A-Za-z0-9_-]+)\\s+qa_evidence_id=([A-Za-z0-9:_-]+)", source_line)
            if match:
                return {"step_id": match.group(1), "evidence_id": match.group(2)}
        return {}

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

    def _page_evidence(self, page):
        try:
            controls = page.locator("button,a[href],input:not([type=hidden]),textarea,select,[role]").evaluate_all("""els => els.slice(0,80).map(el => {
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
                })""") if self.capture_dom else []
            evidence = {
                "url": SensitiveRedactor.redact_url(str(getattr(page, "url", "")))[:2048],
                "title": self._redact_text(str(page.title())[:200]),
                "controls": self._safe_value(controls),
            }
            remaining = self.max_dom_chars
            bounded = []
            for control in controls:
                size = len(json.dumps(control, ensure_ascii=False))
                if size > remaining:
                    break
                bounded.append(control)
                remaining -= size
            evidence["controls"] = bounded
            return evidence
        except Exception:
            return None

    def _install_telemetry(self, page, record):
        record["console_logs"] = []
        record["network_logs"] = []
        record["recent_steps"] = []
        requests = {}
        def publish(kind, entry):
            entry.setdefault('timestamp',datetime.now(timezone.utc).isoformat())
            entry = self._safe_value(entry)
            key = {"console": "console_logs", "network": "network_logs", "step": "recent_steps"}[kind]
            if (kind == "console" and not self.capture_console) or (kind == "network" and not self.capture_network):
                return
            limit = self.max_console_entries if kind == "console" else self.max_network_entries if kind == "network" else 100
            if limit == 0:
                return
            record[key].append(entry)
            del record[key][:-limit]
            self.emit({"type": kind, "session_id": record["session_id"], "page_id": record["page_id"],
                "nodeid": record["nodeid"], "url": SensitiveRedactor.redact_url(getattr(page, "url", "")), "entry": entry})
        def safe_payload(value, depth=0):
            if depth > 4:
                return "[depth limit]"
            if isinstance(value, dict):
                return {str(key): "[REDACTED]" if re.search("password|passwd|secret|token|authorization|cookie|api.?key|email|phone|address|card", str(key), re.I) else safe_payload(item, depth+1) for key, item in list(value.items())[:30]}
            if isinstance(value, list):
                return [safe_payload(item, depth+1) for item in value[:20]]
            return value[:500] if isinstance(value, str) else value
        def started(request):
            if len(requests) >= 100:
                requests.pop(next(iter(requests)))
            requests[id(request)] = time.perf_counter()
        def network(request, failed=False):
            began = requests.pop(id(request), None)
            entry = {"url": request.url[:2048], "method": request.method,
                "duration_ms": round((time.perf_counter()-began)*1000, 1) if began is not None else None}
            try:
                content_type = request.headers.get("content-type", "")
                entry["request"] = {"content_type": content_type,
                    "body": safe_payload(request.post_data_json) if "application/json" in content_type and len(request.post_data or "") <= 8192 else "[not captured: absent, non-JSON or oversized]"}
                response = request.response() if not failed else None
                if response:
                    entry["status"] = response.status
                    content_type = response.headers.get("content-type", "")
                    size = int(response.headers.get("content-length", "0"))
                    # Bodies with unknown/large lengths or non-JSON content remain uncaptured.
                    entry["response"] = {"content_type": content_type,
                        "body": safe_payload(response.json()) if "application/json" in content_type and 0 < size <= 8192 else "[not captured: non-JSON, unknown or oversized length]"}
                else:
                    entry["failure"] = str(request.failure)[:500]
            except Exception:
                entry["body_notice"] = "Body unavailable; request metadata retained"
            publish("network", entry)
        listeners = [("console", lambda message: publish("console", {"level": message.type, "text": message.text[:2000]})),
            ("request", started), ("requestfinished", network),
            ("requestfailed", lambda request: network(request, True))]
        record["listeners"] = listeners
        for name, callback in listeners:
            page.on(name, callback)
        try:
            from playwright.sync_api import Locator
            for method in ("click", "dblclick", "fill", "select_option", "check", "uncheck", "hover", "press"):
                original = getattr(Locator, method)
                self.locator_originals[method] = original
                def instrument(original, method):
                    def wrapped(locator, *args, **kwargs):
                        if getattr(locator, "page", page) is not page:
                            return original(locator, *args, **kwargs)
                        if kwargs.get("trial"):
                            return original(locator, *args, **kwargs)
                        started = time.perf_counter()
                        locator_text = self._redact_text(str(getattr(getattr(locator, "_impl_obj", None), "_selector", ""))[:1000])
                        fingerprint = self._element_fingerprint(locator)
                        location = {}
                        for frame in inspect.stack(context=0)[1:12]:
                            relative = os.path.relpath(frame.filename, os.getcwd()).replace(os.sep, "/")
                            if not relative.startswith("..") and not relative.startswith((".venv/", "venv/")) and "site-packages" not in relative and "qa_platform_live_browser_plugin" not in relative:
                                location = {"file": relative, "line": frame.lineno, **self._recorder_lineage(frame.filename, frame.lineno)}
                                break
                        passed = False
                        try:
                            result = original(locator, *args, **kwargs)
                            passed = True
                            return result
                        finally:
                            if passed and fingerprint and locator_text:
                                record["successful_baselines"][locator_text] = fingerprint
                                if len(record["successful_baselines"]) > 100:
                                    record["successful_baselines"].pop(next(iter(record["successful_baselines"])))
                            elif not passed:
                                record["failed_locator"] = locator_text
                                record["failed_action"] = method
                                record["failed_step_id"] = location.get("step_id")
                                record["failed_evidence_id"] = location.get("evidence_id")
                            publish("step", {"action": method, "locator": locator_text,
                                "status": "PASSED" if passed else "FAILED", "duration_ms": round((time.perf_counter()-started)*1000, 1), **location})
                            evidence = self._page_evidence(page)
                            if evidence:
                                record["last_page_evidence"] = evidence
                            self._capture_frame(page, record)
                    return wrapped
                setattr(Locator, method, instrument(original, method))
        except ImportError:
            pass

    def _remove_telemetry(self, page, record):
        try:
            from playwright.sync_api import Locator
            for method, original in self.locator_originals.items():
                setattr(Locator, method, original)
            self.locator_originals.clear()
            for name, callback in record.get("listeners", []):
                page.remove_listener(name, callback)
        except Exception:
            pass

    def _publish_frame(self, page, record, data):
        if not data:
            return
        record["last_frame"] = data
        self.emit({
            "type": "frame", "session_id": record["session_id"], "page_id": record["page_id"],
            "nodeid": record["nodeid"], "case_name": record["case_name"],
            "url": getattr(page, "url", ""), "status": "running", "mime_type": "image/jpeg", "frame": data,
        })

    def _capture_frame(self, page, record):
        if not self.capture_screenshot:
            return
        # Short tests may close before CDP emits a painted frame. Capture their actual page
        # after navigation/actions and before close; never create a substitute browser/page.
        try:
            data = page.screenshot(type="jpeg", quality=55, timeout=1000)
            self._publish_frame(page, record, base64.b64encode(data).decode("ascii"))
        except Exception:
            pass

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item):
        try:
            from playwright.sync_api import Browser, BrowserContext, Page
        except ImportError:
            yield
            return

        originals = []
        def observe(page):
            if not isinstance(page, Page) or item.nodeid in self.active:
                return
            try:
                self._start_observation(item, page)
            except Exception:
                pass  # Optional telemetry must not change test execution.
        def watch(original):
            def wrapped(instance, *args, **kwargs):
                page = original(instance, *args, **kwargs)
                observe(page)
                return page
            return wrapped
        def capture(original, before=False):
            def wrapped(instance, *args, **kwargs):
                record = self.active.get(item.nodeid)
                def snapshot():
                    if not record:
                        return
                    page = record["page"]
                    if instance is not page and instance is not page.context and instance is not page.context.browser:
                        return
                    self._capture_frame(page, record)
                    evidence = self._page_evidence(page)
                    if evidence:
                        record["last_page_evidence"] = evidence
                if before:
                    snapshot()
                try:
                    return original(instance, *args, **kwargs)
                finally:
                    if not before:
                        snapshot()
            return wrapped
        try:
            for kind in (BrowserContext, Browser):
                original = kind.new_page
                originals.append((kind, "new_page", original))
                kind.new_page = watch(original)
            for kind, method, before in ((Page, "goto", False), (Page, "set_content", False),
                                         (Page, "close", True), (BrowserContext, "close", True), (Browser, "close", True)):
                original = getattr(kind, method)
                originals.append((kind, method, original))
                setattr(kind, method, capture(original, before))
            observe(self._find_page(item))
            yield
        finally:
            record = self.active.get(item.nodeid)
            if record:
                page = record["page"]
                self._capture_frame(page, record)
                self._remove_telemetry(page, record)
                if record["cdp"] is not None:
                    try:
                        record["cdp"].send("Page.stopScreencast")
                        record["cdp"].detach()
                    except Exception:
                        pass
            for kind, method, original in originals:
                setattr(kind, method, original)

    def _start_observation(self, item, page):

        session_id = uuid.uuid4().hex
        page_id = uuid.uuid4().hex
        nodeid = self._nodeid(item)
        record = {"session_id": session_id, "page_id": page_id, "nodeid": nodeid, "case_name": item.name, "page": page, "cdp": None,
            "successful_baselines": {}, "failed_locator": None, "failed_action": None}
        self.active[item.nodeid] = record
        self._install_telemetry(page, record)
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
                    self._publish_frame(page, record, data)
                try:
                    cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
                except Exception:
                    pass

            cdp.on("Page.screencastFrame", on_frame)
            cdp.send("Page.startScreencast", {
                "format": "jpeg", "quality": 55, "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 2,
            })
        except Exception:
            # Other engines still provide actual snapshots at navigation/action boundaries.
            # Continuous CDP frame streaming remains Chromium-only.
            record["cdp"] = None

        try:
            page.on("framenavigated", lambda _frame: self.emit({
                "type": "navigation", "session_id": session_id, "page_id": page_id,
                "nodeid": nodeid, "case_name": item.name,
                "url": getattr(page, "url", ""), "status": "running",
            }))
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
        if report.failed:
            try:
                for entry in reversed(call.excinfo.traceback):
                    filename = str(entry.path)
                    relative = os.path.relpath(filename, os.getcwd()).replace(os.sep, "/")
                    if relative.startswith("..") or "site-packages" in relative or "qa_platform_live_browser_plugin" in relative:
                        continue
                    lineage = self._recorder_lineage(filename, entry.lineno + 1)
                    record.setdefault("failed_step_id", lineage.get("step_id"))
                    record.setdefault("failed_evidence_id", lineage.get("evidence_id"))
                    if lineage:
                        break
                record["failure_snapshot"] = self._failure_snapshot(record)
            except Exception:
                record["failure_snapshot"] = {
                    "status": "PARTIAL",
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "failed_step_id": record.get("failed_step_id"),
                    "failed_evidence_id": record.get("failed_evidence_id"),
                    "url": SensitiveRedactor.redact_url(str(getattr(record["page"], "url", ""))),
                    "failed_locator": self._redact_text(record.get("failed_locator") or "") or None,
                    "original_element_baseline": {"status": "MISSING", "fingerprint": None, "reason": "snapshot_capture_failed"},
                    "storage_state_status": "UNAVAILABLE",
                    "storage_state_ciphertext": None,
                    "replay": {"status": "NOT_STARTED", "safe_point": "captured_url_only", "replayed_steps": [], "not_replayed_steps": [], "message": "Snapshot capture failed; no actions were replayed."},
                    "evidence_gaps": ["snapshot_capture_failed"],
                }
        artifact_dir = os.environ.get("QA_ARTIFACT_DIR")
        if artifact_dir and record.get("last_frame"):
            try:
                with open(os.path.join(artifact_dir, "browser-" + record["session_id"] + "-last.jpg"), "wb") as handle:
                    handle.write(base64.b64decode(record["last_frame"], validate=True))
            except Exception:
                pass
        self.emit({
            "type": "session.finished", "session_id": record["session_id"],
            "page_id": record["page_id"], "nodeid": record["nodeid"], "case_name": item.name,
            "url": getattr(record["page"], "url", ""),
            "status": "passed" if report.passed else "failed" if report.failed else "closed",
            "page_evidence": {**(self._page_evidence(record["page"]) or record.get("last_page_evidence") or {}), "console_logs": record.get("console_logs", []),
                "network_logs": record.get("network_logs", []), "recent_steps": record.get("recent_steps", []),
                **({"failure_snapshot": record["failure_snapshot"]} if record.get("failure_snapshot") else {})},
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
    """Write a standalone plugin and the exact shared redactor into the imported project's run directory."""
    from pathlib import Path

    artifacts_dir = Path(artifacts_dir)
    path = artifacts_dir / f"{LIVE_BROWSER_PLUGIN_NAME}.py"
    path.write_text(LIVE_BROWSER_PLUGIN_SOURCE, encoding="utf-8")
    redactor_source = Path(__file__).resolve().parents[1] / "failure" / "redactor.py"
    (artifacts_dir / "qa_platform_sensitive_redactor.py").write_text(
        redactor_source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return LIVE_BROWSER_PLUGIN_NAME
