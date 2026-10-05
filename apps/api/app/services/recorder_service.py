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
from qa_core.healing.locator_intelligence import rank_locator_candidates

from app.services.browser_proxy import browser_proxy_options, launch_chromium

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
    browser: Any
    context: Any
    page: Any
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


class BrowserRecorderService:
    def __init__(self, decision_service: Any | None = None, decision_settings_service: Any | None = None) -> None:
        self._playwright = None
        self._sessions: dict[str, RecorderSession] = {}
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._decision_service = decision_service
        self._decision_settings_service = decision_settings_service

    async def _start_playwright(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

    async def create_session(self, owner_id: str, data: RecorderSessionCreate) -> RecorderSession:
        async with self._lifecycle_lock:
            proxy = browser_proxy_options()
            playwright = await self._start_playwright()
            try:
                browser = await launch_chromium(playwright, headless=True, **({"proxy": proxy} if proxy else {}))
            except Exception as error:
                raise RuntimeError(
                    "无法启动 Playwright Chromium 或系统 Chrome/Edge。请安装 Playwright Chromium。 "
                    + str(error).splitlines()[0]
                ) from error
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            await context.add_init_script(RECORDER_INIT_SCRIPT)
            page = await context.new_page()
            navigation_error = None
            if data.start_url != "about:blank":
                try:
                    await page.goto(data.start_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as error:
                    # A blocked target must not destroy the browser; the user can retry another URL.
                    navigation_error = str(error)
            session = RecorderSession(
                uuid.uuid4().hex,
                owner_id,
                data.project_id,
                browser,
                context,
                page,
                last_url=page.url,
                requested_url=data.start_url,
                navigation_error=navigation_error,
            )
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
            return {
                "type": "error",
                "message": "浏览器页面已关闭",
                "url": "",
                "state": "CRASHED",
                "steps": session.steps,
            }
        try:
            new_steps: list[dict[str, Any]] = []
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
                        locator_selection = await self._select_locator_candidate(page, event, session.id)
                        if locator_selection:
                            event = {**event, "locator_selection": locator_selection}
                            session.locator_trace = locator_selection["trace"]
                        for step in self.events_to_steps([event]):
                            if not session.steps or self._dedupe_key(session.steps[-1]) != self._dedupe_key(step):
                                session.steps.append(step)
                                new_steps.append(step)
            image = await page.screenshot(type="jpeg", quality=62, timeout=5000)
            tabs = []
            for index, item in enumerate(session.context.pages):
                tabs.append({"index": index, "url": item.url, "title": await item.title(), "active": item is page})
            picked = session.picked_element
            session.picked_element = None
            if picked:
                selection = await self._select_locator_candidate(page, picked, session.id)
                if selection:
                    session.locator_trace = selection["trace"]
                picked = {
                    **picked,
                    "ranked_candidates": rank_locator_candidates(picked.get("candidates") or []),
                    "selection": selection,
                }
            return {
                "type": "frame",
                "url": page.url,
                "title": await page.title(),
                "image": base64.b64encode(image).decode("ascii"),
                "state": session.state,
                "steps": session.steps,
                "new_steps": new_steps,
                "tabs": tabs,
                "picked": picked,
                "locator_trace": session.locator_trace,
            }
        except Exception as error:
            return {
                "type": "error",
                "message": str(error),
                "url": page.url,
                "state": session.state,
                "steps": session.steps,
            }

    async def _select_locator_candidate(
        self, page: Any, event: dict[str, Any], trace_run_id: str
    ) -> dict[str, Any] | None:
        from app.services.locator_decision_service import LocatorDecisionService

        candidates = LocatorDecisionService.generate_candidates(event)
        if not candidates:
            return None
        pipeline = LocatorDecisionService(
            decision_service=self._decision_service,
            settings_service=self._decision_settings_service,
        )
        return await pipeline.decide(
            run_id=trace_run_id,
            event=event,
            candidates=candidates,
            page=page,
            step_id=str(event.get("step_id") or "") or None,
        )

    @staticmethod
    def _candidate_label(candidate: dict[str, Any]) -> str:
        from app.services.locator_decision_service import LocatorDecisionService

        return LocatorDecisionService.format_locator(candidate)

    @staticmethod
    async def _verify_locator_candidate(
        page: Any, candidate: dict[str, Any], event: dict[str, Any]
    ) -> dict[str, bool | None]:
        from app.services.locator_decision_service import LocatorDecisionService

        return await LocatorDecisionService.verify_candidate(page, candidate, event)

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
                candidates = rank_locator_candidates(event.get("candidates") or [])
                selection = event.get("locator_selection") or {}
                candidate = selection.get("selected_candidate") or (
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
        "    raw = (os.getenv('BROWSER_PROXY_URL') or os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')",
        "           or os.getenv('HTTP_PROXY') or os.getenv('http_proxy'))",
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
        "    bypass = os.getenv('BROWSER_PROXY_BYPASS') or os.getenv('NO_PROXY') or os.getenv('no_proxy')",
        "    if bypass:",
        "        proxy['bypass'] = bypass",
        "    return proxy",
        "",
        f"def {test_name}():",
        "    with sync_playwright() as playwright:",
        "        proxy = _browser_proxy()",
        "        channels = [os.getenv('PLAYWRIGHT_CHANNEL'), None, 'msedge', 'chrome']",
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


recorder_service = BrowserRecorderService()
