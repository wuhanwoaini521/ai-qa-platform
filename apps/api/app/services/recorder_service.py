from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlparse

from project_model.models import TestCaseCreate
from pydantic import BaseModel, Field, field_validator
from qa_core.healing.locator_intelligence import rank_locator_candidates

from app.ports.browser_runtime import BrowserRuntime, BrowserRuntimeSession
from app.ports.repository_scope import RepositoryScopeFactory
from app.settings import get_config

RECORDER_INIT_SCRIPT = r"""(() => {
  if (window.__qaRecorderInstalled) return;
  window.__qaRecorderInstalled = true;
  window.__qaRecorderEnabled = true;
  window.__qaRecorderPickMode = false;
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
  const xpathLiteral = value => value.includes("'") ? (value.includes('"') ? `concat('${value.replace(/'/g, "',\"'\",'")}')` : `"${value}"`) : `'${value}'`;
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
    let domDepth=0; for(let node=el; node && node!==document.documentElement; node=node.parentElement) domDepth++;
    if (role && name) {
      const peers=Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,img')).filter(item=>roleFor(item)===role && nameFor(item)===name);
      candidates.push({kind:'role', value:role, name, exact:true, nth:peers.length>1?peers.indexOf(el):null, evidence:{uniqueness:peers.length===1,dom_depth:domDepth}});
    }
    for (const key of ['data-testid','data-test','data-qa']) { const value=el.getAttribute(key); if(value) { const peers=Array.from(document.querySelectorAll('['+key+']')).filter(item=>item.getAttribute(key)===value); candidates.push(key==='data-testid' ? {kind:'test_id',value,nth:peers.length>1?peers.indexOf(el):null,evidence:{uniqueness:peers.length===1,dom_depth:domDepth}} : {kind:'css',value:'['+key+'='+JSON.stringify(value)+']',nth:peers.length>1?peers.indexOf(el):null,evidence:{uniqueness:peers.length===1,dom_depth:domDepth}}); if(key==='data-testid' && !unstable(value)) candidates.push({kind:'xpath',value:'//*[@data-testid='+xpathLiteral(value)+']',evidence:{uniqueness:peers.length===1,dom_depth:domDepth}}); break; } }
    if (el.labels?.length) { const label=Array.from(el.labels).map(item=>item.innerText.trim()).find(Boolean); if(label) candidates.push({kind:'label',value:label,exact:true,evidence:{uniqueness:Array.from(document.querySelectorAll('label')).filter(item=>item.innerText.trim()===label).length===1,dom_depth:domDepth}}); }
    if (el.id && !unstable(el.id)) { candidates.push({kind:'id',value:el.id,evidence:{uniqueness:document.querySelectorAll('#'+CSS.escape(el.id)).length===1,dom_depth:domDepth}}); candidates.push({kind:'xpath',value:'//*[@id='+xpathLiteral(el.id)+']',evidence:{uniqueness:document.querySelectorAll('#'+CSS.escape(el.id)).length===1,dom_depth:domDepth}}); }
    if (el.getAttribute('name')) candidates.push({kind:'name',value:el.getAttribute('name'),evidence:{uniqueness:document.querySelectorAll('[name='+JSON.stringify(el.getAttribute('name'))+']').length===1,dom_depth:domDepth}});
    if (el.getAttribute('placeholder')) { const value=el.getAttribute('placeholder'); candidates.push({kind:'placeholder',value,evidence:{uniqueness:Array.from(document.querySelectorAll('[placeholder]')).filter(item=>item.getAttribute('placeholder')===value).length===1,dom_depth:domDepth}}); }
    const stableClasses=Array.from(el.classList).filter(c=>!unstable(c) && !/[0-9a-f]{8,}/i.test(c)).slice(0,2);
    let css=el.tagName.toLowerCase() + stableClasses.map(c=>'.'+CSS.escape(c)).join('');
    if (!stableClasses.length && el.getAttribute('type')) css += '[type="' + CSS.escape(el.getAttribute('type')) + '"]';
    const cssMatches=Array.from(document.querySelectorAll(css));
    candidates.push({kind:'css',value:css,evidence:{uniqueness:cssMatches.length===1,dom_depth:domDepth}});
    const visibleText=(el.innerText || '').trim().replace(/\s+/g,' ').slice(0,120);
    if (visibleText) candidates.push({kind:'text',value:visibleText,exact:true,evidence:{uniqueness:Array.from(document.querySelectorAll('*')).filter(item=>item.children.length===0 && item.innerText?.trim().replace(/\s+/g,' ')===visibleText).length===1,dom_depth:domDepth,text_stability:!unstable(visibleText)}});
    let nth=null; try { const matches=Array.from(document.querySelectorAll(css)); if(matches.length>1) nth=matches.indexOf(el); } catch {}
    return {tag:el.tagName.toLowerCase(), type:el.getAttribute('type') || '', role, name, value:('value' in el ? el.value : ''), checked:('checked' in el ? el.checked : false), text:(el.innerText || '').trim().slice(0,180), dom_depth:domDepth, url:location.href, candidates, nth, frame_path:framePath()};
  };
  const emit = event => { if (window.__qaRecorderEnabled) window.__qaRecorderEvents.push(event); };
  let inputTimer, clickTimer;
  document.addEventListener('click', event => {
    const raw=event.target, actionable=raw instanceof Element ? raw.closest('button,a,input,textarea,select,[role]') || raw : raw;
    const target=describe(actionable); if(!target) return;
    if(window.__qaRecorderPickMode) { emit({action:'pick',...target}); window.__qaRecorderPickMode=false; event.preventDefault(); event.stopImmediatePropagation(); return; }
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
    action: Literal[
        "navigate",
        "back",
        "scroll",
        "click",
        "double_click",
        "fill",
        "select",
        "check",
        "uncheck",
        "press",
        "hover",
        "wait",
        "assert_visible",
        "assert_text",
        "assert_url",
        "assert_title",
        "assert_count",
    ]
    locator: RecorderLocator | None = None
    frame_path: list[str] = Field(default_factory=list)
    url: str | None = None
    value: str | None = None
    key: str | None = None
    description: str = ""
    locator_decision: dict[str, Any] | None = None


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


class RecorderSaveCaseRequest(BaseModel):
    test_case: TestCaseCreate
    file_path: str = Field(min_length=1, max_length=500)
    test_name: str = Field(min_length=1, max_length=128)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        path = value.replace("\\", "/").strip()
        posix_path = PurePosixPath(path)
        if (
            path.startswith("/")
            or PureWindowsPath(path).is_absolute()
            or PureWindowsPath(path).drive
            or not path.endswith(".py")
            or ".." in posix_path.parts
        ):
            raise ValueError("Recorder file path must be a project-relative .py path.")
        return str(posix_path)

    @field_validator("test_name")
    @classmethod
    def validate_test_name(cls, value: str) -> str:
        if not re.fullmatch(r"test_[A-Za-z0-9_]+", value):
            raise ValueError("Recorder test name must be a valid pytest test function name.")
        return value


class RecorderOptimization(BaseModel):
    steps: list[RecorderStep] = Field(max_length=500)
    reasons: list[str] = Field(max_length=30)


def validate_recording_optimization(raw: list[RecorderStep], optimized: list[RecorderStep]) -> None:
    """Permit only the advertised safe operations, independent of the model's claims."""
    normalized = []
    for step in raw:
        if step.action == "hover":
            continue
        if (
            normalized
            and step.action == "fill"
            and normalized[-1].action == "fill"
            and step.locator == normalized[-1].locator
            and step.frame_path == normalized[-1].frame_path
        ):
            normalized[-1] = step
        else:
            normalized.append(step)

    def meaning(steps):
        return [
            {
                key: value
                for key, value in step.model_dump().items()
                if key not in {"id", "description", "locator_decision"}
            }
            for step in steps
        ]

    if meaning([step for step in optimized if step.action != "hover"]) != meaning(normalized):
        raise ValueError("Optimization changed a business action, target, value or assertion; proposal was rejected.")


@dataclass
class RecorderSession:
    id: str
    owner_id: str
    project_id: str
    runtime_session: BrowserRuntimeSession
    state: str = "READY"
    last_url: str = "about:blank"
    requested_url: str = "about:blank"
    navigation_error: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.monotonic)
    picked_element: dict[str, Any] | None = None
    locator_trace: list[dict[str, Any]] = field(default_factory=list)
    pending_pick_action: str = "click"

    @property
    def browser_session_id(self) -> str:
        return self.runtime_session.id


class BrowserRecorderService:
    def __init__(
        self,
        decision_service: Any | None = None,
        decision_settings_service: Any | None = None,
        browser_runtime: BrowserRuntime | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
    ) -> None:
        if browser_runtime is None:
            from app.container import get_browser_runtime

            browser_runtime = get_browser_runtime()
        self.browser_runtime = browser_runtime
        self.repository_scope = repository_scope
        self._sessions: dict[str, RecorderSession] = {}
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._decision_service = decision_service
        self._decision_settings_service = decision_settings_service

    async def create_session(self, owner_id: str, data: RecorderSessionCreate) -> RecorderSession:
        config = get_config()
        if not config.recorder.enabled or not config.features.recorder:
            raise RuntimeError("Browser recorder is disabled by config/config.yaml.")
        async with self._lifecycle_lock:
            runtime_session = await self.browser_runtime.create_session()
            try:
                await self.browser_runtime.add_init_script(runtime_session.id, RECORDER_INIT_SCRIPT)
            except Exception as error:
                await self.browser_runtime.close_session(runtime_session.id)
                raise RuntimeError(
                    "无法初始化实时浏览器会话。请检查 Playwright 浏览器安装和运行权限。 " + str(error).splitlines()[0]
                ) from error
            navigation_error = None
            if data.start_url != "about:blank":
                try:
                    await self.browser_runtime.navigate(
                        runtime_session.id,
                        data.start_url,
                        timeout_ms=round(config.browser.navigation_timeout_seconds * 1000),
                    )
                except Exception as error:
                    # A blocked target must not destroy the browser; the user can retry another URL.
                    navigation_error = str(error)
            session = RecorderSession(
                id=runtime_session.id,
                owner_id=owner_id,
                project_id=data.project_id,
                runtime_session=runtime_session,
                last_url=runtime_session.current_url,
                requested_url=data.start_url,
                navigation_error=navigation_error,
            )
            session.steps = [RecorderStep.model_validate(step).model_dump(mode="json") for step in data.recovered_steps]
            async with self._lock:
                self._sessions[session.id] = session
        return session

    async def get(self, session_id: str, owner_id: str) -> RecorderSession | None:
        session = self._sessions.get(session_id)
        return session if session and session.owner_id == owner_id else None

    @staticmethod
    def session_status(session: RecorderSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "project_id": session.project_id,
            "state": session.state,
            "url": session.last_url,
            "requested_url": session.requested_url,
            "navigation_error": session.navigation_error,
            "steps": session.steps,
        }

    @staticmethod
    def touch(session: RecorderSession) -> None:
        session.last_activity = asyncio.get_running_loop().time()

    @staticmethod
    def navigation_failed(session: RecorderSession, message: str) -> None:
        session.navigation_error = message

    async def apply_command(self, session: RecorderSession, command: dict[str, Any]) -> str | None:
        runtime_session = await self.browser_runtime.get_session(session.browser_session_id)
        if runtime_session is None:
            raise RuntimeError("Recorder browser session is closed or expired")
        page = await self.browser_runtime.get_page(session.browser_session_id)
        action = command.get("action")
        if action == "navigate":
            target = RecorderSessionCreate(project_id=session.project_id, start_url=command["url"]).start_url
            session.requested_url = target
            try:
                await self.browser_runtime.navigate(session.browser_session_id, target, timeout_ms=30_000)
                session.navigation_error = None
            except Exception as error:
                session.navigation_error = str(error)
                raise
        elif action == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=15_000)
        elif action == "forward":
            await page.go_forward(wait_until="domcontentloaded", timeout=15_000)
        elif action == "reload":
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        elif action == "start":
            session.state = "RECORDING"
            if not session.steps:
                session.steps.extend(self.events_to_steps([{"action": "navigate", "url": page.url}]))
            for frame in page.frames:
                await frame.evaluate("() => {window.__qaRecorderEnabled=true; window.__qaRecorderEvents=[]}")
        elif action == "pause":
            session.state = "PAUSED"
        elif action == "resume":
            session.state = "RECORDING"
        elif action == "stop":
            session.state = "STOPPED"
        elif action == "click":
            await page.mouse.click(command["x"], command["y"])
        elif action == "double_click":
            await page.mouse.dblclick(command["x"], command["y"])
        elif action == "move":
            await page.mouse.move(command["x"], command["y"])
        elif action == "pick_element":
            requested_action = command.get("step_action")
            session.pending_pick_action = (
                requested_action
                if requested_action in {"click", "double_click", "fill", "select", "check", "uncheck", "press", "hover"}
                else "click"
            )
            for frame in page.frames:
                await frame.evaluate("() => { window.__qaRecorderPickMode = true; window.__qaRecorderEnabled = true; }")
        elif action == "wheel":
            await page.mouse.wheel(command.get("delta_x", 0), command.get("delta_y", 0))
        elif action == "type":
            await page.keyboard.insert_text(command.get("text", ""))
        elif action == "press":
            await page.keyboard.press(command["key"])
        elif action == "tab":
            index = int(command["index"])
            try:
                await self.browser_runtime.select_page(session.browser_session_id, index)
            except IndexError:
                pass
        elif action == "add_step":
            session.steps.append(RecorderStep.model_validate(command["step"]).model_dump(mode="json"))
        elif action == "replace_steps":
            raw_steps = command.get("steps")
            if not isinstance(raw_steps, list) or len(raw_steps) > 500:
                raise ValueError("A recorder session can contain at most 500 steps.")
            session.steps = [RecorderStep.model_validate(step).model_dump(mode="json") for step in raw_steps]
        elif action == "edit_step":
            updated = RecorderStep.model_validate(command["step"]).model_dump(mode="json")
            session.steps = [updated if step["id"] == updated["id"] else step for step in session.steps]
        elif action == "delete_step":
            session.steps = [step for step in session.steps if step["id"] != command.get("id")]
        elif action == "reorder":
            order = command.get("ids", [])
            by_id = {step["id"]: step for step in session.steps}
            session.steps = [by_id[item] for item in order if item in by_id] + [
                step for step in session.steps if step["id"] not in order
            ]
        self.touch(session)
        return page.url if action == "navigate" else None

    async def close(self, session_id: str, owner_id: str) -> None:
        session = await self.get(session_id, owner_id)
        if not session:
            return
        async with self._lifecycle_lock:
            async with self._lock:
                if self._sessions.pop(session_id, None) is None:
                    return
            await self.browser_runtime.close_session(session.browser_session_id)

    async def close_all(self) -> None:
        for session in list(self._sessions.values()):
            await self.close(session.id, session.owner_id)

    @staticmethod
    def _is_navigation_context_error(error: Exception) -> bool:
        message = str(error).casefold()
        return any(
            marker in message
            for marker in (
                "execution context was destroyed",
                "most likely because of a navigation",
                "frame was detached",
                "navigation interrupted",
                "navigation in progress",
                "cannot find context with specified id",
            )
        )

    async def page_snapshot(self, session: RecorderSession) -> dict[str, Any]:
        runtime_session = await self.browser_runtime.get_session(session.browser_session_id)
        if runtime_session is None:
            return {
                "type": "error",
                "message": "浏览器会话已关闭或过期",
                "url": "",
                "state": "CRASHED",
                "steps": session.steps,
            }
        page = await self.browser_runtime.get_page(session.browser_session_id)
        try:
            new_steps: list[dict[str, Any]] = []
            if page.url.startswith("chrome-error://"):
                return {
                    "type": "error",
                    "message": "Chrome 显示网络错误页，目标网站没有加载成功。请检查网址、网络或浏览器代理。",
                    "url": page.url,
                    "state": session.state,
                    "steps": session.steps,
                }
            snapshot = await self.browser_runtime.snapshot(
                session.browser_session_id,
                screenshot_type="jpeg",
                screenshot_quality=62,
                full_page=False,
                screenshot_timeout_ms=5_000,
            )
            if session.state == "RECORDING" and page.url != session.last_url:
                step = self.events_to_steps([{"action": "navigate", "url": page.url}])[0]
                session.steps.append(step)
                new_steps.append(step)
            session.last_url = page.url
            for frame in page.frames:
                frame_events = await frame.evaluate("() => window.__qaRecorderDrain ? window.__qaRecorderDrain() : []")
                for event in frame_events:
                    if event.get("action") == "pick":
                        session.picked_element = {**event, "action": session.pending_pick_action}
                        session.pending_pick_action = "click"
                        continue
                    if session.state == "RECORDING":
                        locator_selection = await self._select_locator_candidate(
                            page, event, session.id, session.browser_session_id
                        )
                        if locator_selection:
                            event = {**event, "locator_selection": locator_selection}
                            session.locator_trace = locator_selection["trace"]
                        for step in self.events_to_steps([event]):
                            if not session.steps or self._dedupe_key(session.steps[-1]) != self._dedupe_key(step):
                                session.steps.append(step)
                                new_steps.append(step)
            image = snapshot.screenshot or b""
            tabs = snapshot.tabs
            picked = session.picked_element
            session.picked_element = None
            if picked:
                selection = await self._select_locator_candidate(page, picked, session.id, session.browser_session_id)
                if selection:
                    session.locator_trace = selection["trace"]
                picked = {
                    **picked,
                    "ranked_candidates": rank_locator_candidates(picked.get("candidates") or []),
                    "selection": selection,
                }
            return {
                "type": "frame",
                "url": snapshot.url,
                "title": snapshot.title,
                "image": base64.b64encode(image).decode("ascii"),
                "state": session.state,
                "steps": session.steps,
                "new_steps": new_steps,
                "tabs": tabs,
                "picked": picked,
                "locator_trace": session.locator_trace,
            }
        except Exception as error:
            if self._is_navigation_context_error(error):
                return {
                    "type": "navigating",
                    "url": page.url,
                    "state": session.state,
                    "steps": session.steps,
                }
            return {
                "type": "error",
                "message": str(error),
                "url": page.url,
                "state": session.state,
                "steps": session.steps,
            }

    async def _select_locator_candidate(
        self, page: Any, event: dict[str, Any], trace_run_id: str, browser_session_id: str
    ) -> dict[str, Any] | None:
        from app.services.locator_decision_service import LocatorDecisionService

        candidates = LocatorDecisionService.generate_candidates(event)
        candidates = candidates[: get_config().recorder.candidate_limit]
        if not candidates:
            return None
        pipeline = LocatorDecisionService(
            decision_service=self._decision_service,
            settings_service=self._decision_settings_service,
            browser_runtime=self.browser_runtime,
            repository_scope=self.repository_scope,
        )
        return await pipeline.decide(
            run_id=trace_run_id,
            event=event,
            candidates=candidates,
            browser_session_id=browser_session_id,
            step_id=str(event.get("step_id") or "") or None,
        )

    @staticmethod
    def _candidate_label(candidate: dict[str, Any]) -> str:
        from app.services.locator_decision_service import LocatorDecisionService

        return LocatorDecisionService.format_locator(candidate)

    @staticmethod
    async def _verify_locator_candidate(
        self, browser_session_id: str, candidate: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, bool | None]:
        return await self.browser_runtime.verify_locator(browser_session_id, candidate, event)

    @staticmethod
    def _dedupe_key(step: dict[str, Any]) -> tuple:
        locator = step.get("locator") or {}
        return (
            step.get("action"),
            locator.get("kind"),
            locator.get("value"),
            locator.get("name"),
            step.get("value"),
            step.get("url"),
            step.get("key"),
        )

    @staticmethod
    def events_to_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for event in events:
            action = event.get("action")
            if action not in {
                "navigate",
                "click",
                "double_click",
                "fill",
                "select",
                "check",
                "uncheck",
                "press",
                "hover",
            }:
                continue
            locator_data = None
            locator_decision = None
            if action != "navigate":
                recorder_config = get_config().recorder
                candidates = rank_locator_candidates(event.get("candidates") or [])[: recorder_config.candidate_limit]
                selection = event.get("locator_selection") or {}
                selected = selection.get("selected_candidate")
                if selected is None and recorder_config.locator_strategy != "semantic":
                    selected = next(
                        (item for item in candidates if item.get("kind") == recorder_config.locator_strategy), None
                    )
                candidate = selected or (
                    candidates[0] if candidates else {"kind": "css", "value": event.get("tag", "body")}
                )
                locator_data = {
                    "kind": candidate.get("kind", "css"),
                    "value": str(candidate.get("value", "")),
                    "name": candidate.get("name"),
                    "exact": candidate.get("exact", True),
                    "nth": candidate.get("nth", event.get("nth")),
                }
                locator_decision = selection.get("summary")
            result.append(
                RecorderStep(
                    action=action,
                    locator=locator_data,
                    frame_path=event.get("frame_path", []),
                    url=event.get("url") if action == "navigate" else None,
                    value=str(event.get("value", "")) if action in ("fill", "select") else None,
                    key=event.get("key") if action == "press" else None,
                    description=event.get("name") or event.get("url") or action.replace("_", " ").title(),
                    locator_decision=locator_decision,
                ).model_dump(mode="json", exclude_none=True)
            )
        return result


def _py_literal(value: str | None) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _locator_expression(locator: RecorderLocator | None, frame_path: list[str] | None = None) -> str:
    if locator is None:
        raise ValueError("该步骤缺少 Locator")
    page = "page" + "".join(f".frame_locator({_py_literal(selector)})" for selector in (frame_path or []))
    if locator.kind == "role":
        expression = (
            f"{page}.get_by_role({_py_literal(locator.value)}, name={_py_literal(locator.name)}, exact={locator.exact})"
        )
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
        "from urllib.parse import unquote, urlsplit",
        "from playwright.sync_api import sync_playwright, expect",
        "",
        "def _browser_proxy():",
        "    raw = os.getenv('BROWSER_PROXY_URL')",
        "    if not raw:",
        "        return None",
        "    parsed = urlsplit(raw if '://' in raw else f'http://{raw}')",
        "    if (parsed.scheme not in {'http', 'https', 'socks5'} or not parsed.hostname",
        "            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):",
        "        raise ValueError('BROWSER_PROXY_URL must be an HTTP, HTTPS or SOCKS5 proxy URL')",
        "    proxy = {'server': f\"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}\"}",
        "    if parsed.username:",
        "        proxy['username'] = unquote(parsed.username)",
        "    if parsed.password:",
        "        proxy['password'] = unquote(parsed.password)",
        "    bypass = os.getenv('BROWSER_PROXY_BYPASS')",
        "    if bypass:",
        "        proxy['bypass'] = bypass",
        "    return proxy",
        "",
        f"def {test_name}():",
        "    with sync_playwright() as playwright:",
        "        proxy = _browser_proxy()",
        "        channels = [None, 'msedge', 'chrome']",
        "        browser = None",
        "        launch_error = None",
        "        for channel in dict.fromkeys(channels):",
        "            try:",
        "                browser = playwright.chromium.launch(headless=True, channel=channel, **({'proxy': proxy} if proxy else {}))",
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
        elif step.action == "back":
            lines.append("            page.go_back()")
        elif step.action == "scroll":
            direction = -650 if str(step.value or "down").lower() == "up" else 650
            lines.append(f"            page.mouse.wheel(0, {direction})")
        elif step.action == "wait":
            lines.append(f"            page.wait_for_timeout({int(step.value or '1000')})")
        elif step.action == "assert_url":
            lines.append(f"            expect(page).to_have_url(re.compile({_py_literal(step.value)}))")
        elif step.action == "assert_title":
            lines.append(f"            expect(page).to_have_title(re.compile({_py_literal(step.value)}))")
        else:
            locator = _locator_expression(step.locator, step.frame_path)
            if step.action == "click":
                lines.append(f"            {locator}.click()")
            elif step.action == "double_click":
                lines.append(f"            {locator}.dblclick()")
            elif step.action == "fill":
                lines.append(f"            {locator}.fill({_py_literal(step.value)})")
            elif step.action == "select":
                lines.append(f"            {locator}.select_option(label={_py_literal(step.value)})")
            elif step.action == "check":
                lines.append(f"            {locator}.check()")
            elif step.action == "uncheck":
                lines.append(f"            {locator}.uncheck()")
            elif step.action == "press":
                lines.append(f"            {locator}.press({_py_literal(step.key)})")
            elif step.action == "hover":
                lines.append(f"            {locator}.hover()")
            elif step.action == "assert_visible":
                lines.append(f"            expect({locator}).to_be_visible()")
            elif step.action == "assert_text":
                lines.append(f"            expect({locator}).to_contain_text({_py_literal(step.value)})")
            elif step.action == "assert_count":
                lines.append(f"            expect({locator}).to_have_count({int(step.value or '1')})")
    lines.extend(["        finally:", "            browser.close()", ""])
    return "\n".join(lines)
