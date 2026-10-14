from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlparse

from project_model.models import TestCaseCreate
from pydantic import BaseModel, Field, field_validator, model_validator
from qa_core.failure.redactor import SensitiveRedactor
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
  window.__qaRecorderHovered = null;
  const sensitive = /password|passwd|secret|token|api[-_]?key|authorization|cookie|email|phone|credit|card|ssn|address|first[-_ ]?name|last[-_ ]?name|full[-_ ]?name|birth|\bdob\b|postal|\bzip\b/i;
  const safeText = value => String(value || '').replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/ig, '[redacted]').replace(/\b(?:bearer\s+)?[A-Za-z0-9_-]{32,}\b/ig, '[redacted]').replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[redacted]').replace(/(?:\+\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}/g, '[redacted]').replace(/\s+/g, ' ').trim().slice(0, 180);
  const safeUrl = () => { try { const url=new URL(location.href); url.username=''; url.password=''; url.search=''; url.hash=''; return url.href; } catch { return location.origin; } };
  const containsPrivateData = value => /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\b\d{3}-\d{2}-\d{4}\b|(?:\+\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}|\b[A-Za-z0-9_-]{32,}\b/i.test(String(value || ''));
  const isSensitive = el => (el instanceof Element) && (['password','email','tel'].includes((el.getAttribute('type') || '').toLowerCase()) || [el.id,el.getAttribute('name'),el.getAttribute('aria-label'),el.getAttribute('placeholder'),el.getAttribute('autocomplete')].some(value => value && sensitive.test(value)));
  let overlayHost, overlayBox, overlayLabel, describedElement;
  const ensureOverlay = () => {
    if (overlayHost?.isConnected) return;
    if (!document.documentElement) return;
    overlayHost=document.createElement('div');
    overlayHost.setAttribute('aria-hidden','true');
    overlayHost.style.cssText='all:initial!important;position:fixed!important;inset:0!important;z-index:2147483647!important;pointer-events:none!important;contain:strict!important;overflow:hidden!important;';
    const root=overlayHost.attachShadow({mode:'open'});
    const style=document.createElement('style');
    style.textContent=':host{all:initial}#box{position:fixed;display:none;box-sizing:border-box;border:2px solid #6d5dfc;background:rgba(109,93,252,.08);border-radius:3px;pointer-events:none}#label{position:fixed;display:none;max-width:min(360px,80vw);padding:4px 7px;border-radius:4px;background:#29234f;color:#fff;font:12px/1.35 -apple-system,BlinkMacSystemFont,sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 2px 8px #0004}';
    overlayBox=document.createElement('div'); overlayBox.id='box';
    overlayLabel=document.createElement('div'); overlayLabel.id='label';
    root.append(style,overlayBox,overlayLabel);
    document.documentElement.append(overlayHost);
  };
  const showHover = el => {
    ensureOverlay();
    if (!overlayBox || !window.__qaRecorderPickMode || !(el instanceof Element)) { if(overlayBox) overlayBox.style.display='none'; if(overlayLabel) overlayLabel.style.display='none'; window.__qaRecorderHovered=null; describedElement=null; hoveredElement=null; return; }
    const rect=el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    overlayBox.style.cssText=`position:fixed;display:block;box-sizing:border-box;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;border:2px solid #6d5dfc;background:rgba(109,93,252,.08);border-radius:3px;pointer-events:none`;
    if(el!==describedElement) { window.__qaRecorderHovered=describe(el); describedElement=el; }
    const item=window.__qaRecorderHovered;
    const text=`${item?.role || item?.tag || 'element'} · ${item?.name || item?.text || '(unnamed)'}`;
    overlayLabel.textContent=text;
    overlayLabel.style.cssText=`position:fixed;display:block;left:${Math.max(4,Math.min(rect.left,innerWidth-360))}px;top:${Math.max(2,rect.top-27)}px;max-width:min(360px,80vw);padding:4px 7px;border-radius:4px;background:#29234f;color:#fff;font:12px/1.35 -apple-system,BlinkMacSystemFont,sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 2px 8px #0004`;
    window.__qaRecorderHovered=item;
  };
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
    const labelled = el.getAttribute('aria-label'); if (labelled) return safeText(labelled);
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) { const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim(); if (text) return safeText(text); }
    if (el.labels?.length) { const text = Array.from(el.labels).map(label => label.innerText).join(' ').trim(); if (text) return safeText(text); }
    return safeText(el.getAttribute('alt') || el.getAttribute('title') || (isSensitive(el) ? '' : el.innerText) || '');
  };
  const unstable = value => !value || /^\d+$/.test(value) || /^[0-9a-f]{8,}$/i.test(value) || /\d{5,}/.test(value);
  const xpathLiteral = value => value.includes("'") ? (value.includes('"') ? `concat('${value.replace(/'/g, "',\"'\",'")}')` : `"${value}"`) : `'${value}'`;
  const framePath = () => {
    const path=[]; let frame=window.frameElement;
    while(frame) {
      const tag=frame.tagName.toLowerCase(), id=frame.id, testId=frame.getAttribute('data-testid'), name=frame.getAttribute('name'), title=frame.getAttribute('title');
      let selector;
      if(testId && !containsPrivateData(testId)) selector=`${tag}[data-testid="${CSS.escape(testId)}"]`;
      else if(id && !unstable(id) && !containsPrivateData(id)) selector=`#${CSS.escape(id)}`;
      else if(name && !unstable(name) && !containsPrivateData(name)) selector=`${tag}[name="${CSS.escape(name)}"]`;
      else if(title && !containsPrivateData(title)) selector=`${tag}[title="${CSS.escape(title)}"]`;
      else { const siblings=Array.from(frame.ownerDocument.querySelectorAll(tag)); selector=`${tag}:nth-of-type(${siblings.indexOf(frame)+1})`; }
      path.unshift(selector);
      try { frame=frame.ownerDocument.defaultView?.frameElement || null; } catch { frame=null; }
    }
    return path;
  };
  const describe = el => {
    if (!(el instanceof Element)) return null;
    const role = roleFor(el), name = nameFor(el), candidates = [];
    const sensitiveValue=isSensitive(el);
    const attributes = {};
    for (const attribute of Array.from(el.attributes).slice(0,24)) {
      if (!sensitive.test(attribute.name) && (!sensitiveValue || ['type','name'].includes(attribute.name))) attributes[attribute.name] = safeText(attribute.value).slice(0,120);
    }
    const rect=el.getBoundingClientRect();
    const parent=el.parentElement;
    const siblings=parent ? Array.from(parent.children).slice(0,12).map(item=>({tag:item.tagName.toLowerCase(),role:roleFor(item),name:isSensitive(item) ? '' : nameFor(item)})) : [];
    const shadowPath=[];
    for(let root=el.getRootNode(); root instanceof ShadowRoot; root=root.host.getRootNode()) {
      const host=root.host; shadowPath.unshift(host.id && !sensitive.test(host.id) && !containsPrivateData(host.id) ? `#${CSS.escape(host.id)}` : host.tagName.toLowerCase());
    }
    let domDepth=0; for(let node=el; node && node!==document.documentElement; node=node.parentElement) domDepth++;
    if (role && name && !name.includes('[redacted]')) {
      const peers=Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,img')).filter(item=>roleFor(item)===role && nameFor(item)===name);
      candidates.push({kind:'role', value:role, name, exact:true, nth:peers.length>1?peers.indexOf(el):null, evidence:{match_count:peers.length,uniqueness:peers.length===1,dom_depth:domDepth}});
    }
    for (const key of ['data-testid','data-test','data-qa']) { const value=el.getAttribute(key); if(value && !sensitive.test(value) && !containsPrivateData(value)) { const peers=Array.from(document.querySelectorAll('['+key+']')).filter(item=>item.getAttribute(key)===value); candidates.push(key==='data-testid' ? {kind:'test_id',value,nth:peers.length>1?peers.indexOf(el):null,evidence:{uniqueness:peers.length===1,dom_depth:domDepth}} : {kind:'css',value:'['+key+'='+JSON.stringify(value)+']',nth:peers.length>1?peers.indexOf(el):null,evidence:{uniqueness:peers.length===1,dom_depth:domDepth}}); if(key==='data-testid' && !unstable(value)) candidates.push({kind:'xpath',value:'//*[@data-testid='+xpathLiteral(value)+']',evidence:{uniqueness:peers.length===1,dom_depth:domDepth}}); break; } }
    if (el.labels?.length) { const label=Array.from(el.labels).map(item=>item.innerText.trim()).find(Boolean); if(label && !containsPrivateData(label)) candidates.push({kind:'label',value:label,exact:true,evidence:{uniqueness:Array.from(document.querySelectorAll('label')).filter(item=>item.innerText.trim()===label).length===1,dom_depth:domDepth}}); }
    if (el.id && !unstable(el.id) && !containsPrivateData(el.id)) { candidates.push({kind:'id',value:el.id,evidence:{uniqueness:document.querySelectorAll('#'+CSS.escape(el.id)).length===1,dom_depth:domDepth}}); candidates.push({kind:'xpath',value:'//*[@id='+xpathLiteral(el.id)+']',evidence:{uniqueness:document.querySelectorAll('#'+CSS.escape(el.id)).length===1,dom_depth:domDepth}}); }
    if (el.getAttribute('name') && !containsPrivateData(el.getAttribute('name'))) candidates.push({kind:'name',value:el.getAttribute('name'),evidence:{uniqueness:document.querySelectorAll('[name='+JSON.stringify(el.getAttribute('name'))+']').length===1,dom_depth:domDepth}});
    if (el.getAttribute('placeholder') && !containsPrivateData(el.getAttribute('placeholder'))) { const value=el.getAttribute('placeholder'); candidates.push({kind:'placeholder',value,evidence:{uniqueness:Array.from(document.querySelectorAll('[placeholder]')).filter(item=>item.getAttribute('placeholder')===value).length===1,dom_depth:domDepth}}); }
    const stableClasses=Array.from(el.classList).filter(c=>!unstable(c) && !containsPrivateData(c) && !/[0-9a-f]{8,}/i.test(c)).slice(0,2);
    let css=el.tagName.toLowerCase() + stableClasses.map(c=>'.'+CSS.escape(c)).join('');
    if (!stableClasses.length && el.getAttribute('type')) css += '[type="' + CSS.escape(el.getAttribute('type')) + '"]';
    const cssMatches=Array.from(document.querySelectorAll(css));
    candidates.push({kind:'css',value:css,evidence:{uniqueness:cssMatches.length===1,dom_depth:domDepth}});
    const rawText=sensitiveValue ? '' : el.innerText || '';
    const visibleText=safeText(rawText).slice(0,120);
    if (visibleText && !containsPrivateData(rawText)) candidates.push({kind:'text',value:visibleText,exact:true,evidence:{uniqueness:null,dom_depth:domDepth,text_stability:!unstable(visibleText)}});
    let nth=null; try { const matches=Array.from(document.querySelectorAll(css)); if(matches.length>1) nth=matches.indexOf(el); } catch {}
    const visible=!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);
    const actionable=el.matches('button,a[href],input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=checkbox],[role=radio],[tabindex]:not([tabindex="-1"])');
    const rawValue='value' in el ? String(el.value) : '';
    const safeValue=sensitiveValue ? null : safeText(rawValue);
    const valueRedacted=sensitiveValue || (!!rawValue && safeValue!==rawValue);
    const selectedOptionText=!sensitiveValue && el.tagName.toLowerCase()==='select' ? safeText(el.selectedOptions[0]?.textContent || '') : '';
    return {tag:el.tagName.toLowerCase(), type:el.getAttribute('type') || '', id:el.id && !sensitive.test(el.id) ? safeText(el.id) : '', class: safeText(Array.from(el.classList).filter(value=>!sensitive.test(value)).slice(0,8).join(' ')), role, name, text:sensitiveValue ? '' : safeText(el.innerText || ''), value:valueRedacted ? null : safeValue, value_redacted:valueRedacted, checked:('checked' in el ? el.checked : false), selected_option_text:selectedOptionText, attributes, parent_summary:parent ? `${parent.tagName.toLowerCase()} ${safeText(parent.getAttribute('aria-label') || (parent.id && !sensitive.test(parent.id) ? parent.id : '')).slice(0,80)}` : '', children:sensitiveValue ? [] : Array.from(el.children).slice(0,8).map(child=>({tag:child.tagName.toLowerCase(),role:roleFor(child),name:nameFor(child)})), siblings, bounding_box:{x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)}, visible, actionable, frame_path:framePath(), shadow_path:shadowPath, url:safeUrl(), title:safeText(document.title), captured_at:new Date().toISOString(), candidates, nth};
  };
  const emit = event => { if (window.__qaRecorderEnabled) window.__qaRecorderEvents.push(event); };
  const interactive = 'button,a[href],input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=checkbox],[role=radio],[tabindex]:not([tabindex="-1"])';
  const eventElement = event => {
    const path=event.composedPath?.() || [event.target];
    return path.find(item=>item instanceof Element && item.matches(interactive)) || path.find(item=>item instanceof Element) || null;
  };
  const inputTimers=new WeakMap();
  let clickTimer, hovered, hoverTimer, hoveredElement;
  for (const type of ['pointerdown','pointerup','mousedown','mouseup','touchstart','touchend']) window.addEventListener(type, event => {
    if(window.__qaRecorderPickMode) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  window.addEventListener('click', event => {
    const target=describe(eventElement(event)); if(!target) return;
    if(window.__qaRecorderPickMode) {
      emit({action:'pick',...target}); window.__qaRecorderPickMode=false; showHover(null);
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if(target.tag==='select' || ['checkbox','radio'].includes(target.type)) return;
    if(event.detail>1) { clearTimeout(clickTimer); emit({action:'double_click',...target}); return; }
    clickTimer=setTimeout(()=>emit({action:'click',...target}),260);
  }, true);
  document.addEventListener('input', event => {
    const raw=event.target, target=describe(raw); if(!target || !['input','textarea'].includes(target.tag) || ['checkbox','radio','submit','button'].includes(target.type)) return;
    clearTimeout(inputTimers.get(raw));
    inputTimers.set(raw,setTimeout(()=>emit({action:'fill',...describe(raw)}),400));
  }, true);
  document.addEventListener('change', event => {
    const target=describe(event.target); if(!target) return;
    if(target.tag==='select') emit({action:'select',...target});
    else if(target.type==='checkbox' || target.type==='radio') emit({action:target.checked?'check':'uncheck',...target});
  }, true);
  window.addEventListener('keydown', event => {
    if(window.__qaRecorderPickMode) {
      if(event.key==='Escape') { window.__qaRecorderPickMode=false; showHover(null); }
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (!['Enter','Tab','Escape','ArrowDown','ArrowUp','ArrowLeft','ArrowRight',' '].includes(event.key)) return;
    const target=describe(event.target); if(target) emit({action:'press',...target,key:event.key});
  }, true);
  window.addEventListener('keyup', event => {
    if(window.__qaRecorderPickMode) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  document.addEventListener('pointermove', event => {
    if(!window.__qaRecorderPickMode) return;
    const target=eventElement(event); if(!target || target===hoveredElement) return;
    hoveredElement=target; showHover(target);
  }, true);
  const syncHighlight=()=>{ if(window.__qaRecorderPickMode && hoveredElement?.isConnected) showHover(hoveredElement); };
  window.addEventListener('scroll',syncHighlight,true);
  window.addEventListener('resize',syncHighlight);
  const observeChanges=()=>{if(document.documentElement)new MutationObserver(syncHighlight).observe(document.documentElement,{subtree:true,childList:true,attributes:true});};
  if(document.documentElement) observeChanges(); else document.addEventListener('DOMContentLoaded',observeChanges,{once:true});
  document.addEventListener('pointerover', event => {
    const target=eventElement(event); if(!target || target===hovered || window.__qaRecorderPickMode) return;
    hovered=target; clearTimeout(hoverTimer); hoverTimer=setTimeout(()=>{const item=describe(target); if(item && item.name) emit({action:'hover',...item});},650);
  }, true);
  const originalPush=history.pushState.bind(history), originalReplace=history.replaceState.bind(history);
  history.pushState=(...args)=>{const result=originalPush(...args); emit({action:'navigate',url:safeUrl()}); return result;};
  history.replaceState=(...args)=>{const result=originalReplace(...args); emit({action:'navigate',url:safeUrl()}); return result;};
  window.addEventListener('popstate',()=>emit({action:'navigate',url:safeUrl()}));
  window.__qaRecorderSetPickMode=enabled=>{window.__qaRecorderPickMode=!!enabled;hoveredElement=null;if(!enabled)showHover(null);};
  window.__qaRecorderClearHover=()=>showHover(null);
  window.__qaRecorderDrain=()=>window.__qaRecorderEvents.splice(0);
})();"""


class RecorderLocator(BaseModel):
    kind: Literal["role", "test_id", "label", "placeholder", "id", "name", "css", "text", "xpath"]
    value: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=500)
    exact: bool = True
    nth: int | None = None


class RecorderStep(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12], min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
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
    frame_path: list[str] = Field(default_factory=list, max_length=8)
    url: str | None = Field(default=None, max_length=2048)
    value: str | None = Field(default=None, max_length=4000)
    value_redacted: bool = False
    secret_env_var: str | None = None
    select_by_value: bool = False
    key: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=160)
    locator_decision: dict[str, Any] | None = None
    evidence: RecorderStepEvidence | None = None

    @model_validator(mode="after")
    def redact_private_values(self):
        element = self.evidence.element if self.evidence else {}
        attributes = element.get("attributes") or {}
        sensitive_target = bool(
            str(element.get("type") or "").lower() in {"password", "email", "tel"}
            or re.search(
                r"password|secret|token|api[-_]?key|authorization|cookie|email|phone|card|ssn|address|first[-_ ]?name|last[-_ ]?name|full[-_ ]?name|birth|\bdob\b|postal|\bzip\b",
                " ".join(
                    [
                        str(element.get("id") or ""),
                        str(element.get("name") or ""),
                        str(element.get("placeholder") or ""),
                        *(str(value) for value in attributes.values()),
                    ]
                ),
                re.I,
            )
        )
        if self.value is not None:
            safe_value = _safe_recorder_text(self.value)
            if self.value_redacted or sensitive_target or safe_value != self.value:
                self.value = None
                self.value_redacted = True
        return self

    @field_validator("url")
    @classmethod
    def redact_recorded_url(cls, value: str | None) -> str | None:
        return SensitiveRedactor.redact_url(value) if value is not None else None

    @field_validator("secret_env_var")
    @classmethod
    def validate_secret_env_var(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value):
            raise ValueError("Secret environment variable must be a valid name of at most 64 characters")
        return value


class RecorderStepEvidence(BaseModel):
    schema_version: Literal[1] = 1
    element: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    locator_candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    decision: dict[str, Any] = Field(default_factory=dict)
    decision_history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    ai_analysis: dict[str, Any] | None = None
    jev_analysis: dict[str, Any] | None = None
    status: Literal["available", "partial", "stale"] = "available"
    missing: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def limit_size(self):
        def sanitize(value):
            if isinstance(value, dict):
                return {
                    key: "[REDACTED]"
                    if re.search(
                        r"password|secret|token|api[-_]?key|authorization|cookie|email|phone|card|ssn|address",
                        str(key),
                        re.I,
                    )
                    and item is not None
                    else sanitize(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, str):
                text = SensitiveRedactor.redact_text(value)
                text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED]", text, flags=re.IGNORECASE)
                return re.sub(r"(?<!\w)\+?\d[\d ().-]{8,}\d(?!\w)", "[REDACTED]", text)
            return value

        for key in (
            "element",
            "context",
            "locator_candidates",
            "decision",
            "decision_history",
            "ai_analysis",
            "jev_analysis",
        ):
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, sanitize(value))
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False)) > 32_000:
            raise ValueError("Recorder step evidence exceeds 32 KB")
        return self


class RecorderLocatorAIResponse(BaseModel):
    candidate_id: str | None = None
    alternative_candidate_id: str | None = None
    reason: str = Field(default="", max_length=500)
    risk: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    confidence: float | None = Field(default=None, ge=0, le=1)


class RecorderSessionCreate(BaseModel):
    project_id: str
    start_url: str = "about:blank"
    recovered_steps: list[dict[str, Any]] = Field(default_factory=list, max_length=500)

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
    steps: list[RecorderStep] = Field(max_length=500)

    @model_validator(mode="after")
    def reject_embedded_sensitive_values(self):
        if any(step.value_redacted and step.value for step in self.steps):
            raise ValueError(
                "Sensitive recorder values must be supplied through an environment variable, not stored in a step."
            )
        return self


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


def normalize_recording_steps(raw: list[RecorderStep]) -> list[RecorderStep]:
    normalized = []
    for step in raw:
        if step.action == "hover":
            continue
        if (
            normalized
            and step.action == "fill"
            and normalized[-1].action == "fill"
            and normalized[-1].locator == step.locator
            and normalized[-1].frame_path == step.frame_path
        ):
            normalized[-1] = step
        else:
            normalized.append(step)
    return normalized


def validate_recording_optimization(raw: list[RecorderStep], optimized: list[RecorderStep]) -> None:
    """Permit only the advertised safe operations, independent of the model's claims."""
    normalized = normalize_recording_steps(raw)

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


def _safe_recorder_text(value: Any, limit: int = 500) -> str:
    text = SensitiveRedactor.redact_text(str(value or ""))
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b\d{3}-\d{2}-\d{4}\b|(?:\+\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}", "[REDACTED]", text
    )
    return text[:limit]


def _same_recorder_target(
    original_step: dict[str, Any],
    latest_step: dict[str, Any],
    original_evidence: RecorderStepEvidence,
    latest_evidence: RecorderStepEvidence,
) -> bool:
    candidate_fields = ("candidate_id", "kind", "value", "name", "exact", "nth", "locator")

    def candidate_identity(evidence: RecorderStepEvidence) -> list[tuple[Any, ...]]:
        return [tuple(candidate.get(key) for key in candidate_fields) for candidate in evidence.locator_candidates]

    return (
        original_step.get("action") == latest_step.get("action")
        and original_step.get("frame_path", []) == latest_step.get("frame_path", [])
        and original_evidence.element == latest_evidence.element
        and original_evidence.context.get("url") == latest_evidence.context.get("url")
        and original_evidence.context.get("frame_path", []) == latest_evidence.context.get("frame_path", [])
        and candidate_identity(original_evidence) == candidate_identity(latest_evidence)
    )


def _step_evidence(event: dict[str, Any], selection: dict[str, Any]) -> RecorderStepEvidence:
    element_fields = ("tag", "id", "class", "type", "role", "name", "text", "attributes", "checked")
    element = {key: event[key] for key in element_fields if key in event}
    element = SensitiveRedactor.redact_value(element)
    if isinstance(element.get("attributes"), dict):
        element["attributes"] = {
            key: value
            for key, value in element["attributes"].items()
            if not re.search(r"password|secret|token|key|cookie|email|phone|card|ssn|address", key, re.I)
        }
    context_fields = (
        "url",
        "title",
        "frame_path",
        "shadow_path",
        "parent_summary",
        "children",
        "siblings",
        "bounding_box",
        "visible",
        "actionable",
        "captured_at",
        "dom_depth",
    )
    context = {key: event[key] for key in context_fields if key in event}
    context = SensitiveRedactor.redact_value(context)
    candidates = selection.get("ranked_candidates") or event.get("candidates") or []
    summary = selection.get("summary") or {}
    verification = selection.get("verification") or {}
    missing = [key for key in ("bounding_box", "parent_summary", "frame_path") if key not in event]
    return RecorderStepEvidence(
        element=element,
        context=context,
        locator_candidates=SensitiveRedactor.redact_value(candidates[:16]),
        decision={
            "selected_candidate_id": summary.get("candidate_id"),
            "source": summary.get("provider"),
            "reason": summary.get("fallback_reason"),
            "verification": SensitiveRedactor.redact_value(verification),
        },
        jev_analysis=(
            {
                "status": "available",
                "provider": "jev",
                "candidate_id": summary.get("candidate_id"),
                "summary": SensitiveRedactor.redact_value(summary),
                "reason": None,
            }
            if summary.get("provider") == "jev" and not summary.get("fallback_used")
            else None
        ),
        status="partial" if missing else "available",
        missing=missing,
    )


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
    last_locator_verification: dict[str, Any] | None = None
    steps_revision: int = 0

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
                    navigation_error = SensitiveRedactor.redact_text(str(error))
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
            session.steps_revision = 1 if session.steps else 0
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
            "url": SensitiveRedactor.redact_url(session.last_url),
            "requested_url": SensitiveRedactor.redact_url(session.requested_url),
            "navigation_error": SensitiveRedactor.redact_text(session.navigation_error or "") or None,
            "steps": session.steps,
            "steps_revision": session.steps_revision,
        }

    @staticmethod
    def element_evidence_bundle(session: RecorderSession) -> dict[str, Any]:
        steps = []
        for raw_step in getattr(session, "steps", []):
            step = RecorderStep.model_validate(raw_step)
            if step.evidence is None:
                continue
            evidence = step.evidence.model_dump(mode="json")
            safe_candidates = []
            for candidate in evidence["locator_candidates"]:
                safe = SensitiveRedactor.redact_value(candidate)
                value = candidate.get("value")
                name = candidate.get("name")
                if (
                    not isinstance(value, str)
                    or safe.get("value") != value
                    or _safe_recorder_text(value, 2000) != value
                    or "[redacted]" in value.casefold()
                    or "***redacted***" in value.casefold()
                    or (
                        isinstance(name, str)
                        and (_safe_recorder_text(name, 500) != name or "[redacted]" in name.casefold())
                    )
                ):
                    continue
                safe_candidates.append(
                    {
                        key: safe[key]
                        for key in (
                            "candidate_id",
                            "kind",
                            "value",
                            "name",
                            "exact",
                            "nth",
                            "evidence",
                            "verification",
                            "static_score",
                            "strategy",
                        )
                        if key in safe
                    }
                )
            evidence["locator_candidates"] = safe_candidates
            locator = step.locator.model_dump(mode="json") if step.locator else None
            safe_locator = SensitiveRedactor.redact_value(locator) if locator else None
            if safe_locator and (
                safe_locator.get("value") != locator.get("value")
                or _safe_recorder_text(str(locator.get("value") or ""), 2000) != locator.get("value")
                or "[redacted]" in str(locator.get("value") or "").casefold()
                or "***redacted***" in str(locator.get("value") or "").casefold()
                or (
                    isinstance(locator.get("name"), str)
                    and (
                        _safe_recorder_text(locator["name"], 500) != locator["name"]
                        or "[redacted]" in locator["name"].casefold()
                    )
                )
            ):
                safe_locator = None
            steps.append(
                {
                    "step_id": step.id,
                    "evidence_id": f"recorder:{step.id}",
                    "action": step.action,
                    "url": SensitiveRedactor.redact_url(str(step.evidence.context.get("url") or "")),
                    "frame_path": evidence["context"].get("frame_path", []),
                    "locator": safe_locator,
                    "evidence": evidence,
                }
            )
        bundle = {
            "schema": "element-evidence-bundle",
            "version": "v1.0",
            "source": "smart-recorder",
            "session_id": getattr(session, "id", ""),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "steps": steps,
        }
        if len(json.dumps(bundle, ensure_ascii=False)) > 1_000_000:
            raise ValueError("Recorder element evidence bundle exceeds 1 MB")
        return bundle

    @staticmethod
    def touch(session: RecorderSession) -> None:
        session.last_activity = asyncio.get_running_loop().time()

    @staticmethod
    def navigation_failed(session: RecorderSession, message: str) -> None:
        session.navigation_error = SensitiveRedactor.redact_text(message)

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
                session.navigation_error = SensitiveRedactor.redact_text(str(error))
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
                await frame.evaluate(
                    "() => { window.__qaRecorderSetPickMode?.(true); window.__qaRecorderPickMode = true; window.__qaRecorderEnabled = true; }"
                )
        elif action == "cancel_pick":
            session.pending_pick_action = "click"
            for frame in page.frames:
                await frame.evaluate("() => window.__qaRecorderSetPickMode?.(false)")
        elif action == "clear_hover":
            for frame in page.frames:
                await frame.evaluate("() => window.__qaRecorderClearHover?.()")
        elif action == "verify_locator":
            await self._verify_and_select_locator(session, command)
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
        if action in {"start", "add_step", "replace_steps", "edit_step", "delete_step", "reorder", "verify_locator"}:
            session.steps_revision += 1
        self.touch(session)
        return SensitiveRedactor.redact_url(page.url) if action == "navigate" else None

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
                    "url": SensitiveRedactor.redact_url(page.url),
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
            hovered_element = None
            for frame in page.frames:
                frame_hover = await frame.evaluate("() => window.__qaRecorderHovered || null")
                if frame_hover:
                    hovered_element = frame_hover
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
            if new_steps:
                session.steps_revision += 1
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
                    "evidence": _step_evidence(picked, selection or {}).model_dump(mode="json"),
                }
            return {
                "type": "frame",
                "url": SensitiveRedactor.redact_url(snapshot.url),
                "title": _safe_recorder_text(snapshot.title, 180),
                "image": base64.b64encode(image).decode("ascii"),
                "state": session.state,
                "steps": session.steps,
                "steps_revision": session.steps_revision,
                "new_steps": new_steps,
                "tabs": tabs,
                "picked": picked,
                "locator_trace": session.locator_trace,
                "hovered": hovered_element,
                "locator_verification": session.last_locator_verification,
            }
        except Exception as error:
            if self._is_navigation_context_error(error):
                return {
                    "type": "navigating",
                    "url": SensitiveRedactor.redact_url(page.url),
                    "state": session.state,
                    "steps": session.steps,
                    "steps_revision": session.steps_revision,
                }
            return {
                "type": "error",
                "message": SensitiveRedactor.redact_text(str(error)),
                "url": SensitiveRedactor.redact_url(page.url),
                "state": session.state,
                "steps": session.steps,
                "steps_revision": session.steps_revision,
            }

    async def _verify_and_select_locator(self, session: RecorderSession, command: dict[str, Any]) -> None:
        step_id = str(command.get("step_id") or "")
        step = next((item for item in session.steps if item.get("id") == step_id), None)
        if step is None:
            raise LookupError("Recorder step not found")
        evidence = RecorderStepEvidence.model_validate(step.get("evidence") or {})
        candidate_id = str(command.get("candidate_id") or "")
        candidate = next(
            (item for item in evidence.locator_candidates if item.get("candidate_id") == candidate_id), None
        )
        if candidate is None and command.get("source") == "manual" and step.get("locator"):
            candidate = {**step["locator"], "candidate_id": "manual"}
            evidence.locator_candidates.append(candidate)
            candidate_id = "manual"
        if candidate is None:
            raise ValueError("Locator candidate is not in this step's evidence")
        source = command.get("source", "manual")
        if source not in {"ai", "jev", "manual"}:
            raise ValueError("Invalid locator decision source")
        if source == "ai" and not (
            evidence.ai_analysis
            and evidence.ai_analysis.get("status") == "available"
            and evidence.ai_analysis.get("candidate_id") == candidate_id
        ):
            raise ValueError("AI has not recommended this candidate")
        if source == "jev" and not (
            (evidence.jev_analysis or {}).get("candidate_id") == candidate_id
            or (
                evidence.decision.get("source") == "jev"
                and evidence.decision.get("selected_candidate_id") == candidate_id
            )
        ):
            raise ValueError("Jev has not recommended this candidate")
        if len(evidence.decision_history) >= 30:
            raise ValueError("Locator decision history is full; start a new recorder step before further decisions.")
        verification = await self.browser_runtime.verify_locator(
            session.browser_session_id,
            candidate,
            {"action": step["action"], "frame_path": evidence.context.get("frame_path", [])},
        )
        candidate["verification"] = verification
        evidence.decision_history.append(
            SensitiveRedactor.redact_value(
                {
                    "candidate_id": candidate_id,
                    "source": source,
                    "reason": str(command.get("reason") or (evidence.ai_analysis or {}).get("reason") or "")[:200],
                    "verification": {
                        key: verification.get(key)
                        for key in ("match_count", "unique", "visible", "enabled", "editable", "clickable", "verified")
                        if key in verification
                    },
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
        if verification.get("verified"):
            page = await self.browser_runtime.get_page(session.browser_session_id)
            evidence.context["revalidated_url"] = SensitiveRedactor.redact_url(page.url)
            evidence.status = "partial" if evidence.missing else "available"
        else:
            evidence.status = "stale"
        if verification.get("verified"):
            step["locator"] = {
                key: candidate[key] for key in ("kind", "value", "name", "exact", "nth") if key in candidate
            }
            step["frame_path"] = evidence.context.get("frame_path", [])
            evidence.decision = {
                "selected_candidate_id": candidate_id,
                "source": source,
                "reason": command.get("reason") or (evidence.ai_analysis or {}).get("reason"),
                "verification": verification,
            }
            step["locator_decision"] = {
                "provider": source,
                "candidate_id": candidate_id,
                "candidate_count": len(evidence.locator_candidates),
                "verified": True,
            }
        step["evidence"] = evidence.model_dump(mode="json")
        session.steps = [step if item.get("id") == step_id else item for item in session.steps]
        session.steps_revision += 1
        session.last_locator_verification = {
            "step_id": step_id,
            "candidate_id": candidate_id,
            "source": source,
            **verification,
        }

    async def _select_locator_candidate(
        self, page: Any, event: dict[str, Any], trace_run_id: str, browser_session_id: str
    ) -> dict[str, Any] | None:
        from app.services.locator_decision_service import LocatorDecisionService

        candidates = LocatorDecisionService.generate_candidates(event)
        candidates = candidates[: get_config().recorder.candidate_limit]
        if not candidates:
            return None
        for candidate in candidates:
            candidate["verification"] = await self.browser_runtime.verify_locator(browser_session_id, candidate, event)
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

    async def _refresh_recorder_candidates(
        self, session: RecorderSession, step: dict[str, Any], evidence: RecorderStepEvidence
    ) -> None:
        event = {**evidence.element, **evidence.context, "action": step["action"]}
        for candidate in evidence.locator_candidates:
            candidate["verification"] = await self.browser_runtime.verify_locator(
                session.browser_session_id, candidate, event
            )
        page = await self.browser_runtime.get_page(session.browser_session_id)
        current_url = SensitiveRedactor.redact_url(page.url)
        recorded_url = SensitiveRedactor.redact_url(str(evidence.context.get("url") or ""))
        if current_url != recorded_url or not any(
            (item.get("verification") or {}).get("verified") for item in evidence.locator_candidates
        ):
            evidence.status = "stale"
        elif evidence.status == "stale":
            evidence.status = "partial" if evidence.missing else "available"
        evidence.context["revalidated_url"] = current_url

    async def analyze_locator_with_ai(self, session: RecorderSession, step_id: str) -> dict[str, Any]:
        from app.services.ai_runtime import build_ai_orchestrator

        step = next((item for item in session.steps if item.get("id") == step_id), None)
        if step is None:
            raise LookupError("Recorder step not found")
        evidence = RecorderStepEvidence.model_validate(step.get("evidence") or {})
        await self._refresh_recorder_candidates(session, step, evidence)
        verified = [
            item for item in evidence.locator_candidates if (item.get("verification") or {}).get("verified") is True
        ]
        if not verified:
            analysis = {
                "status": "unavailable",
                "provider": None,
                "candidate_id": None,
                "reason": "no_verified_candidates",
            }
        else:
            prompt_data = SensitiveRedactor.redact_value(
                {
                    "element": evidence.element,
                    "context": evidence.context,
                    "action": step["action"],
                    "verified_candidates": [
                        {
                            key: item.get(key)
                            for key in (
                                "candidate_id",
                                "kind",
                                "value",
                                "name",
                                "exact",
                                "nth",
                                "locator",
                                "evidence",
                                "verification",
                            )
                        }
                        for item in verified
                    ],
                }
            )
            from qa_core.ai.models import AICompletionRequest

            response = await build_ai_orchestrator().complete(
                AICompletionRequest(
                    prompt=json.dumps(prompt_data, ensure_ascii=False, separators=(",", ":")),
                    system_instruction=(
                        "You are reviewing browser locator evidence. Recommend only a supplied verified candidate_id; "
                        "never invent or alter locators. Consider semantic clarity, stability and ambiguity. "
                        "If none is suitable, abstain. Return only the requested structured analysis."
                    ),
                    response_schema=RecorderLocatorAIResponse,
                    prompt_id="recorder_locator_analysis",
                    prompt_version="1",
                    temperature=0.1,
                    max_tokens=1200,
                    timeout_seconds=20,
                    max_retries=0,
                )
            )
            if response.provider == "fake" or response.fallback_used:
                analysis = {
                    "status": "unavailable",
                    "provider": response.provider,
                    "model": response.model,
                    "candidate_id": None,
                    "reason": "real_ai_provider_unavailable",
                    "invocation_id": response.invocation_id,
                }
            else:
                parsed = RecorderLocatorAIResponse.model_validate(response.structured_data or {})
                valid_ids = {item.get("candidate_id") for item in verified}
                valid_choice = parsed.candidate_id is None or parsed.candidate_id in valid_ids
                analysis = {
                    "status": "available" if valid_choice else "invalid",
                    "provider": response.provider,
                    "model": response.model,
                    "invocation_id": response.invocation_id,
                    **parsed.model_dump(),
                    "candidate_id": parsed.candidate_id if valid_choice else None,
                    "alternative_candidate_id": parsed.alternative_candidate_id
                    if parsed.alternative_candidate_id in valid_ids
                    else None,
                    "reason": parsed.reason if valid_choice else "model_selected_unverified_candidate",
                }
        latest_step = next((item for item in session.steps if item.get("id") == step_id), None)
        if latest_step is not None:
            latest_evidence = RecorderStepEvidence.model_validate(latest_step.get("evidence") or {})
            if _same_recorder_target(step, latest_step, evidence, latest_evidence):
                latest_evidence.locator_candidates = evidence.locator_candidates
                latest_evidence.status = evidence.status
                latest_evidence.context["revalidated_url"] = evidence.context.get("revalidated_url")
            else:
                analysis = {
                    **analysis,
                    "status": "invalid",
                    "candidate_id": None,
                    "alternative_candidate_id": None,
                    "reason": "step_changed_during_analysis",
                }
            latest_evidence.ai_analysis = analysis
            latest_step["evidence"] = latest_evidence.model_dump(mode="json")
            session.steps_revision += 1
        return analysis

    async def request_jev_locator_decision(self, session: RecorderSession, step_id: str) -> dict[str, Any]:
        from app.services.locator_decision_service import LocatorDecisionService

        step = next((item for item in session.steps if item.get("id") == step_id), None)
        if step is None:
            raise LookupError("Recorder step not found")
        evidence = RecorderStepEvidence.model_validate(step.get("evidence") or {})
        if not evidence.locator_candidates:
            raise ValueError("This step has no recorded locator candidates")
        await self._refresh_recorder_candidates(session, step, evidence)
        event = {**evidence.element, **evidence.context, "action": step["action"]}
        pipeline = LocatorDecisionService(
            decision_service=self._decision_service,
            settings_service=self._decision_settings_service,
            browser_runtime=self.browser_runtime,
            repository_scope=self.repository_scope,
        )
        selection = await pipeline.decide(
            run_id=session.id,
            event=event,
            candidates=evidence.locator_candidates,
            browser_session_id=session.browser_session_id,
            step_id=step_id,
        )
        summary = selection["summary"]
        jev = summary.get("provider") == "jev" and not summary.get("fallback_used")
        analysis = {
            "status": "available" if jev else "unavailable",
            "provider": summary.get("provider"),
            "candidate_id": summary.get("candidate_id") if jev else None,
            "summary": summary,
            "reason": summary.get("fallback_reason"),
        }
        latest_step = next((item for item in session.steps if item.get("id") == step_id), None)
        if latest_step is not None:
            latest_evidence = RecorderStepEvidence.model_validate(latest_step.get("evidence") or {})
            if _same_recorder_target(step, latest_step, evidence, latest_evidence):
                latest_evidence.locator_candidates = selection.get("ranked_candidates", evidence.locator_candidates)
                latest_evidence.status = evidence.status
                latest_evidence.context["revalidated_url"] = evidence.context.get("revalidated_url")
            else:
                analysis = {
                    **analysis,
                    "status": "unavailable",
                    "candidate_id": None,
                    "reason": "step_changed_during_analysis",
                }
            latest_evidence.jev_analysis = analysis
            latest_step["evidence"] = latest_evidence.model_dump(mode="json")
            session.steps_revision += 1
        session.locator_trace = selection.get("trace", [])
        return analysis

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
            evidence = _step_evidence(event, selection) if action != "navigate" else None
            raw_value = event.get("value")
            value_redacted = bool(event.get("value_redacted")) or (
                action in {"fill", "select"}
                and raw_value is not None
                and _safe_recorder_text(raw_value) != str(raw_value)
            )
            step = RecorderStep(
                action=action,
                locator=locator_data,
                frame_path=event.get("frame_path", []),
                url=_safe_recorder_text(event.get("url"), 2048) if action == "navigate" else None,
                value=(None if value_redacted else _safe_recorder_text(raw_value))
                if action in ("fill", "select")
                else None,
                select_by_value=action == "select",
                key=event.get("key") if action == "press" else None,
                description=_safe_recorder_text(
                    event.get("name") or event.get("url") or action.replace("_", " ").title(), 160
                ),
                locator_decision=locator_decision,
                evidence=evidence,
                value_redacted=value_redacted,
            )
            result.append(step.model_dump(mode="json", exclude_none=True))
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
        step_lines_start = len(lines)
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
                if step.value_redacted:
                    variable = step.secret_env_var or f"QA_RECORDER_SECRET_{step.id.upper()}"
                    local_name = f"recorder_secret_{index}"
                    lines.append(f"            {local_name} = os.getenv({_py_literal(variable)})")
                    lines.append(
                        f"            if {local_name} is None: raise RuntimeError({_py_literal('Set environment variable ' + variable)})"
                    )
                    lines.append(f"            {locator}.fill({local_name})")
                else:
                    lines.append(f"            {locator}.fill({_py_literal(step.value)})")
            elif step.action == "select":
                option_key = "value" if step.select_by_value else "label"
                if step.value_redacted:
                    variable = step.secret_env_var or f"QA_RECORDER_SECRET_{step.id.upper()}"
                    local_name = f"recorder_secret_{index}"
                    lines.append(f"            {local_name} = os.getenv({_py_literal(variable)})")
                    lines.append(
                        f"            if {local_name} is None: raise RuntimeError({_py_literal('Set environment variable ' + variable)})"
                    )
                    lines.append(f"            {locator}.select_option({option_key}={local_name})")
                else:
                    lines.append(f"            {locator}.select_option({option_key}={_py_literal(step.value)})")
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
        marker = f"  # qa_step_id={step.id} qa_evidence_id=recorder:{step.id}"
        for line_index in range(step_lines_start + 1, len(lines)):
            if lines[line_index].strip() and not lines[line_index].lstrip().startswith("#"):
                lines[line_index] += marker
    lines.extend(["        finally:", "            browser.close()", ""])
    return "\n".join(lines)
