from __future__ import annotations

import json
from typing import Any


async def verify_locator(page: Any, candidate: dict[str, Any], event: dict[str, Any]) -> dict[str, bool | None]:
    locator = page
    try:
        for selector in event.get("frame_path") or []:
            locator = locator.frame_locator(selector)
        kind = candidate.get("kind")
        value = str(candidate.get("value") or "")
        if kind == "role":
            locator = locator.get_by_role(value, name=candidate.get("name"), exact=candidate.get("exact", True))
        elif kind == "test_id":
            locator = locator.get_by_test_id(value)
        elif kind == "label":
            locator = locator.get_by_label(value, exact=candidate.get("exact", True))
        elif kind == "placeholder":
            locator = locator.get_by_placeholder(value, exact=candidate.get("exact", True))
        elif kind == "text":
            locator = locator.get_by_text(value, exact=candidate.get("exact", True))
        elif kind == "id":
            locator = locator.locator(f"[id={json.dumps(value)}]")
        elif kind == "name":
            locator = locator.locator(f"[name={json.dumps(value)}]")
        else:
            locator = locator.locator(value if kind != "xpath" or value.startswith("xpath=") else f"xpath={value}")
        count = await locator.count()
        target = locator.nth(candidate["nth"]) if candidate.get("nth") is not None else locator
        visible = count > 0 and await target.is_visible()
        action = str(event.get("action") or "")
        interactive = action in {"click", "double_click", "fill", "select", "check", "uncheck", "press", "hover"}
        enabled = count > 0 and await target.is_enabled() if interactive else None
        editable = count > 0 and await target.is_editable() if action in {"fill", "press"} else None
        clickable = None
        if action in {"click", "double_click"}:
            clickable = bool(
                await target.evaluate("""el => {
                  const tag = el.tagName.toLowerCase();
                  const role = el.getAttribute('role');
                  const interactive = (tag === 'a' && Boolean(el.getAttribute('href')))
                    || ['button', 'input', 'textarea', 'select', 'summary'].includes(tag)
                    || ['button', 'link', 'checkbox', 'radio', 'switch', 'menuitem'].includes(role);
                  const rect = el.getBoundingClientRect();
                  if (!interactive || rect.width <= 0 || rect.height <= 0) return false;
                  const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
                  if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return true;
                  const hit = document.elementFromPoint(x, y);
                  return hit === el || el.contains(hit);
                }""")
            )
        unique = count == 1
        return {
            "unique": unique,
            "visible": visible,
            "enabled": enabled,
            "editable": editable,
            "clickable": clickable,
            "verified": unique
            and visible
            and enabled is not False
            and editable is not False
            and clickable is not False,
        }
    except Exception:
        return {
            "unique": False,
            "visible": False,
            "enabled": False,
            "editable": False,
            "clickable": False,
            "verified": False,
        }
