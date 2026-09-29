from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

RECORDER_INIT_SCRIPT = r"""(() => {
  if (window.__qaRecorderInstalled) return;
  window.__qaRecorderInstalled = true;
  window.__qaRecorderEnabled = true;
  window.__qaRecorderEvents = [];
  const roleFor = el => {
    const explicit = el.getAttribute('role'); if (explicit) return explicit.split(/\s+/)[0];
    const tag = el.tagName.toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (['button','submit','reset','image'].includes(type)) return 'button';
      if (type === 'checkbox') return 'checkbox'; if (type === 'radio') return 'radio';
      if (['email','text','password','search','tel','url','number'].includes(type)) return 'textbox';
    }
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'img') return 'img';
    return null;
  };
  const nameFor = el => {
    const labelled = el.getAttribute('aria-label'); if (labelled) return labelled.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) { const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim(); if (text) return text; }
    if (el.labels?.length) { const text = Array.from(el.labels).map(label => label.innerText).join(' ').trim(); if (text) return text; }
    return (el.getAttribute('alt') || el.getAttribute('title') || el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  };
  const unstable = value => !value || /^\d+$/.test(value) || /^[0-9a-f]{8,}$/i.test(value) || /\d{5,}/.test(value);
  const framePath = () => {
    const path=[]; let frame=window.frameElement;
    while(frame) {
      const tag=frame.tagName.toLowerCase(), id=frame.id, testId=frame.getAttribute('data-testid'), name=frame.getAttribute('name'), title=frame.getAttribute('title');
      let selector;
      if(testId) selector=`${tag}[data-testid="${CSS.escape(testId)}"]`;
      else if(id && !unstable(id)) selector=`#${CSS.escape(id)}`;
      else if(name && !unstable(name)) selector=`${tag}[name="${CSS.escape(name)}"]`;
      else if(title) selector=`${tag}[title="${CSS.escape(title)}"]`;
      else { const siblings=Array.from(frame.ownerDocument.querySelectorAll(tag)); selector=`${tag}:nth-of-type(${siblings.indexOf(frame)+1})`; }
      path.unshift(selector);
      try { frame=frame.ownerDocument.defaultView?.frameElement || null; } catch { frame=null; }
    }
    return path;
  };
  const describe = el => {
    if (!(el instanceof Element)) return null;
    const role = roleFor(el), name = nameFor(el), candidates = [];
    if (role && name) {
      const peers=Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,img')).filter(item=>roleFor(item)===role && nameFor(item)===name);
      candidates.push({kind:'role', value:role, name, exact:true, nth:peers.length>1?peers.indexOf(el):null});
    }
    for (const key of ['data-testid','data-test','data-qa']) { const value=el.getAttribute(key); if(value) { candidates.push({kind:'test_id',value,nth:Array.from(document.querySelectorAll('['+key+']')).filter(item=>item.getAttribute(key)===value).length>1?Array.from(document.querySelectorAll('['+key+']')).filter(item=>item.getAttribute(key)===value).indexOf(el):null}); break; } }
    if (el.id && !unstable(el.id)) candidates.push({kind:'id',value:el.id});
    if (el.getAttribute('name')) candidates.push({kind:'name',value:el.getAttribute('name')});
    if (el.getAttribute('placeholder')) candidates.push({kind:'placeholder',value:el.getAttribute('placeholder')});
    const stableClasses=Array.from(el.classList).filter(c=>!unstable(c) && !/[0-9a-f]{8,}/i.test(c)).slice(0,2);
    let css=el.tagName.toLowerCase() + stableClasses.map(c=>'.'+CSS.escape(c)).join('');
    if (!stableClasses.length && el.getAttribute('type')) css += '[type="' + CSS.escape(el.getAttribute('type')) + '"]';
    candidates.push({kind:'css',value:css});
    if (name) candidates.push({kind:'text',value:name,exact:true});
    let nth=null; try { const matches=Array.from(document.querySelectorAll(css)); if(matches.length>1) nth=matches.indexOf(el); } catch {}
    return {tag:el.tagName.toLowerCase(), type:el.getAttribute('type') || '', role, name, value:('value' in el ? el.value : ''), checked:('checked' in el ? el.checked : false), text:(el.innerText || '').trim().slice(0,180), url:location.href, candidates, nth, frame_path:framePath()};
  };
  const emit = event => { if (window.__qaRecorderEnabled) window.__qaRecorderEvents.push(event); };
  let inputTimer, clickTimer;
  document.addEventListener('click', event => {
    const target=describe(event.target); if(!target) return;
    if(target.tag==='select' || ['checkbox','radio'].includes(target.type)) return;
    if(event.detail>1) { clearTimeout(clickTimer); emit({action:'double_click',...target}); return; }
    clickTimer=setTimeout(()=>emit({action:'click',...target}),260);
  }, true);
  document.addEventListener('input', event => {
    const target=describe(event.target); if(!target || !['input','textarea'].includes(target.tag) || ['checkbox','radio','submit','button'].includes(target.type)) return;
    clearTimeout(inputTimer); inputTimer=setTimeout(()=>emit({action:'fill',...describe(event.target)}),400);
  }, true);
  document.addEventListener('change', event => {
    const target=describe(event.target); if(!target) return;
    if(target.tag==='select') emit({action:'select',...target});
    else if(target.type==='checkbox' || target.type==='radio') emit({action:target.checked?'check':'uncheck',...target});
  }, true);
  document.addEventListener('keydown', event => {
    if (!['Enter','Tab','Escape','ArrowDown','ArrowUp','ArrowLeft','ArrowRight',' '].includes(event.key)) return;
    const target=describe(event.target); if(target) emit({action:'press',...target,key:event.key});
  }, true);
  let hovered, hoverTimer;
  document.addEventListener('pointerover', event => {
    const target=event.target; if(!(target instanceof Element) || target===hovered) return;
    hovered=target; clearTimeout(hoverTimer); hoverTimer=setTimeout(()=>{const item=describe(target); if(item && item.name) emit({action:'hover',...item});},650);
  }, true);
  const originalPush=history.pushState.bind(history), originalReplace=history.replaceState.bind(history);
  history.pushState=(...args)=>{const result=originalPush(...args); emit({action:'navigate',url:location.href}); return result;};
  history.replaceState=(...args)=>{const result=originalReplace(...args); emit({action:'navigate',url:location.href}); return result;};
  window.addEventListener('popstate',()=>emit({action:'navigate',url:location.href}));
  window.__qaRecorderDrain=()=>window.__qaRecorderEvents.splice(0);
})();"""


class RecorderLocator(BaseModel):
    kind: Literal["role", "test_id", "label", "placeholder", "id", "name", "css", "text", "xpath"]
    value: str
    name: str | None = None
    exact: bool = True
    nth: int | None = None


class RecorderStep(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    action: Literal["navigate", "click", "double_click", "fill", "select", "check", "uncheck", "press", "hover", "wait", "assert_visible", "assert_text", "assert_url", "assert_title", "assert_count"]
    locator: RecorderLocator | None = None
    frame_path: list[str] = Field(default_factory=list)
    url: str | None = None
    value: str | None = None
    key: str | None = None
    description: str = ""


class RecorderSessionCreate(BaseModel):
    project_id: str
    start_url: str = "about:blank"
    recovered_steps: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("start_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if value != "about:blank" and parsed.scheme not in ("http", "https"):
            raise ValueError("仅支持 http/https 网页地址")
        if parsed.username or parsed.password:
            raise ValueError("URL 不能包含用户名或密码")
        return value


class RecorderGenerateRequest(BaseModel):
    case_name: str = "recorded_case"
    file_path: str = "tests/test_recorded_case.py"
    test_name: str = "test_recorded_case"
    steps: list[RecorderStep]


@dataclass
class RecorderSession:
    id: str
    owner_id: str
    project_id: str
    browser: Any
    context: Any
    page: Any
    state: str = "READY"
    last_url: str = "about:blank"
    steps: list[dict[str, Any]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.monotonic)


class BrowserRecorderService:
    def __init__(self) -> None:
        self._playwright = None
        self._sessions: dict[str, RecorderSession] = {}
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()

    async def _start_playwright(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

    async def create_session(self, owner_id: str, data: RecorderSessionCreate) -> RecorderSession:
        async with self._lifecycle_lock:
            playwright = await self._start_playwright()
            browser = None
            launch_errors: list[str] = []
            for kwargs in ({"headless": True}, {"headless": True, "channel": "msedge"}, {"headless": True, "channel": "chrome"}):
                try:
                    browser = await playwright.chromium.launch(**kwargs)
                    break
                except Exception as error:
                    launch_errors.append(str(error).splitlines()[0])
            if browser is None:
                raise RuntimeError("无法启动 Chromium。请安装 Playwright Chromium：uv run playwright install chromium。 " + " | ".join(launch_errors))
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            await context.add_init_script(RECORDER_INIT_SCRIPT)
            page = await context.new_page()
            try:
                if data.start_url != "about:blank":
                    await page.goto(data.start_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                await context.close()
                await browser.close()
                raise
            session = RecorderSession(uuid.uuid4().hex, owner_id, data.project_id, browser, context, page, last_url=page.url)
            session.steps = [RecorderStep.model_validate(step).model_dump(mode="json") for step in data.recovered_steps]
            context.on("page", lambda new_page: setattr(session, "page", new_page))
            async with self._lock:
                self._sessions[session.id] = session
        return session

    async def get(self, session_id: str, owner_id: str) -> RecorderSession | None:
        session = self._sessions.get(session_id)
        return session if session and session.owner_id == owner_id else None

    async def close(self, session_id: str, owner_id: str) -> None:
        session = await self.get(session_id, owner_id)
        if not session:
            return
        async with self._lifecycle_lock:
            async with self._lock:
                if self._sessions.pop(session_id, None) is None:
                    return
            await session.context.close()
            await session.browser.close()
            if not self._sessions and self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

    async def close_all(self) -> None:
        for session in list(self._sessions.values()):
            await self.close(session.id, session.owner_id)

    async def page_snapshot(self, session: RecorderSession) -> dict[str, Any]:
        page = session.page
        if page.is_closed():
            return {"type": "error", "message": "浏览器页面已关闭", "url": "", "state": "CRASHED", "steps": session.steps}
        try:
            new_steps: list[dict[str, Any]] = []
            if session.state == "RECORDING" and page.url != session.last_url:
                step = self.events_to_steps([{"action": "navigate", "url": page.url}])[0]
                session.steps.append(step)
                new_steps.append(step)
            session.last_url = page.url
            for frame in page.frames:
                frame_events = await frame.evaluate("() => window.__qaRecorderDrain ? window.__qaRecorderDrain() : []")
                if session.state == "RECORDING":
                    for event in frame_events:
                        for step in self.events_to_steps([event]):
                            if not session.steps or self._dedupe_key(session.steps[-1]) != self._dedupe_key(step):
                                session.steps.append(step)
                                new_steps.append(step)
            image = await page.screenshot(type="jpeg", quality=62, timeout=5000)
            tabs = []
            for index, item in enumerate(session.context.pages):
                tabs.append({"index": index, "url": item.url, "title": await item.title(), "active": item is page})
            return {"type": "frame", "url": page.url, "title": await page.title(), "image": base64.b64encode(image).decode("ascii"), "state": session.state, "steps": session.steps, "new_steps": new_steps, "tabs": tabs}
        except Exception as error:
            return {"type": "error", "message": str(error), "url": page.url, "state": session.state, "steps": session.steps}

    @staticmethod
    def _dedupe_key(step: dict[str, Any]) -> tuple:
        locator = step.get("locator") or {}
        return (step.get("action"), locator.get("kind"), locator.get("value"), locator.get("name"), step.get("value"), step.get("url"), step.get("key"))

    @staticmethod
    def events_to_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for event in events:
            action = event.get("action")
            if action not in {"navigate", "click", "double_click", "fill", "select", "check", "uncheck", "press", "hover"}:
                continue
            locator_data = None
            if action != "navigate":
                candidates = event.get("candidates") or []
                candidate = candidates[0] if candidates else {"kind": "css", "value": event.get("tag", "body")}
                locator_data = {"kind": candidate.get("kind", "css"), "value": str(candidate.get("value", "")), "name": candidate.get("name"), "exact": candidate.get("exact", True), "nth": candidate.get("nth", event.get("nth"))}
            result.append(RecorderStep(action=action, locator=locator_data, frame_path=event.get("frame_path", []), url=event.get("url") if action == "navigate" else None, value=str(event.get("value", "")) if action in ("fill", "select") else None, key=event.get("key") if action == "press" else None, description=event.get("name") or event.get("url") or action.replace("_", " ").title()).model_dump(mode="json"))
        return result


def _py_literal(value: str | None) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _locator_expression(locator: RecorderLocator | None, frame_path: list[str] | None = None) -> str:
    if locator is None:
        raise ValueError("该步骤缺少 Locator")
    page = "page" + "".join(f".frame_locator({_py_literal(selector)})" for selector in (frame_path or []))
    if locator.kind == "role":
        expression = f"{page}.get_by_role({_py_literal(locator.value)}, name={_py_literal(locator.name)}, exact={locator.exact})"
    elif locator.kind == "test_id":
        expression = f"{page}.get_by_test_id({_py_literal(locator.value)})"
    elif locator.kind == "label":
        expression = f"{page}.get_by_label({_py_literal(locator.value)}, exact={locator.exact})"
    elif locator.kind == "placeholder":
        expression = f"{page}.get_by_placeholder({_py_literal(locator.value)}, exact={locator.exact})"
    elif locator.kind == "id":
        expression = f"{page}.locator({_py_literal('#' + locator.value)})"
    elif locator.kind == "name":
        expression = f"{page}.locator({_py_literal('[name=' + json.dumps(locator.value) + ']')})"
    elif locator.kind == "text":
        expression = f"{page}.get_by_text({_py_literal(locator.value)}, exact={locator.exact})"
    elif locator.kind == "xpath":
        expression = f"{page}.locator({_py_literal('xpath=' + locator.value)})"
    else:
        expression = f"{page}.locator({_py_literal(locator.value)})"
    if locator.nth is not None:
        expression += f".nth({locator.nth})"
    return expression


def generate_python_case(request: RecorderGenerateRequest) -> str:
    test_name = re.sub(r"\W+", "_", request.test_name).strip("_") or "test_recorded_case"
    if test_name[0].isdigit():
        test_name = "test_" + test_name
    if not test_name.startswith("test_"):
        test_name = "test_" + test_name
    lines = [
        "import os",
        "import re",
        "from playwright.sync_api import sync_playwright, expect",
        "",
        f"def {test_name}():",
        "    with sync_playwright() as playwright:",
        "        channels = [os.getenv('PLAYWRIGHT_CHANNEL'), None, 'msedge', 'chrome']",
        "        browser = None",
        "        launch_error = None",
        "        for channel in dict.fromkeys(channels):",
        "            try:",
        "                browser = playwright.chromium.launch(headless=True, channel=channel)",
        "                break",
        "            except Exception as error:",
        "                launch_error = error",
        "        if browser is None:",
        "            raise launch_error",
        "        try:",
        "            page = browser.new_page()",
    ]
    for index, step in enumerate(request.steps, start=1):
        lines.append(f"            # Step {index}: {step.description or step.action}")
        if step.action == "navigate":
            lines.append(f"            page.goto({_py_literal(step.url)})")
        elif step.action == "wait":
            lines.append(f"            page.wait_for_timeout({int(step.value or '1000')})")
        elif step.action == "assert_url":
            lines.append(f"            expect(page).to_have_url(re.compile({_py_literal(step.value)}))")
        elif step.action == "assert_title":
            lines.append(f"            expect(page).to_have_title(re.compile({_py_literal(step.value)}))")
        else:
            locator = _locator_expression(step.locator, step.frame_path)
            if step.action == "click": lines.append(f"            {locator}.click()")
            elif step.action == "double_click": lines.append(f"            {locator}.dblclick()")
            elif step.action == "fill": lines.append(f"            {locator}.fill({_py_literal(step.value)})")
            elif step.action == "select": lines.append(f"            {locator}.select_option(label={_py_literal(step.value)})")
            elif step.action == "check": lines.append(f"            {locator}.check()")
            elif step.action == "uncheck": lines.append(f"            {locator}.uncheck()")
            elif step.action == "press": lines.append(f"            {locator}.press({_py_literal(step.key)})")
            elif step.action == "hover": lines.append(f"            {locator}.hover()")
            elif step.action == "assert_visible": lines.append(f"            expect({locator}).to_be_visible()")
            elif step.action == "assert_text": lines.append(f"            expect({locator}).to_contain_text({_py_literal(step.value)})")
            elif step.action == "assert_count": lines.append(f"            expect({locator}).to_have_count({int(step.value or '1')})")
    lines.extend(["        finally:", "            browser.close()", ""])
    return "\n".join(lines)


recorder_service = BrowserRecorderService()
