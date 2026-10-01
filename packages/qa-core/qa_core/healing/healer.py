from __future__ import annotations

import json
import re
from collections import Counter
from html.parser import HTMLParser

from qa_core.healing.locator_intelligence import rank_locator_candidates
from qa_core.healing.models import LocatorCandidate, LocatorRepairProposal


class _DOMTargets(HTMLParser):
    """Collect only selectors backed by attributes/text present in the snapshot."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[dict[str, str]] = []
        self._text: list[str] = []
        self._tag = ""
        self._attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        for key in ("data-testid", "data-test", "data-qa"):
            if values.get(key):
                self.targets.append({"kind": "test_id", "value": values[key]})
                break
        if values.get("aria-label"):
            self.targets.append({"kind": "label", "value": values["aria-label"]})
        if values.get("placeholder"):
            self.targets.append({"kind": "placeholder", "value": values["placeholder"]})
        if values.get("id"):
            self.targets.append({"kind": "id", "value": values["id"]})
        if values.get("name"):
            self.targets.append({"kind": "name", "value": values["name"]})
        self._tag, self._attrs, self._text = tag, values, []

    def handle_data(self, data: str) -> None:
        self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        text = " ".join(part for part in self._text if part)
        if tag == self._tag and text and self._tag in {"button", "a", "label"}:
            self.targets.append({"kind": "text", "value": text[:120]})
            self.targets.append(
                {"kind": "role", "value": "button" if self._tag == "button" else "link", "name": text[:120]}
            )


class NoLocatorCandidateError(ValueError):
    """The observed DOM does not support a distinct replacement locator."""


class LocatorHealer:
    """Proposes robust selector replacements without silently modifying code."""

    @classmethod
    def generate_repair_proposal(
        cls,
        old_locator: str,
        dom_snapshot: str = "",
        error_message: str = "",
        file_path: str | None = None,
    ) -> LocatorRepairProposal:
        if not old_locator.strip():
            raise NoLocatorCandidateError("No failed locator was recorded; no replacement is recommended.")
        candidates = [
            candidate
            for candidate in cls._generate_candidates(old_locator, dom_snapshot)
            if candidate.selector.strip() != old_locator.strip()
        ]
        if not candidates:
            raise NoLocatorCandidateError(
                "The DOM provides no distinct, evidence-backed locator candidate; no replacement is recommended."
            )
        best = candidates[0]

        diff = f"- locator('{old_locator}')\n+ locator('{best.selector}')"

        return LocatorRepairProposal(
            old_locator=old_locator,
            proposed_locator=best.selector,
            confidence=best.confidence,
            strategy=best.strategy,
            reason=best.reason,
            code_diff=diff,
            file_path=file_path,
            applied=False,
        )

    @classmethod
    def _generate_candidates(cls, old_locator: str, dom: str) -> list[LocatorCandidate]:
        if not dom.strip():
            return []
        parser = _DOMTargets()
        try:
            parser.feed(dom)
        except Exception:
            return []

        ignored = {"button", "input", "div", "span", "a", "locator", "get", "by", "xpath"}
        old_tokens = {token.lower() for token in re.findall(r"[\w]+", old_locator) if len(token) > 2} - ignored
        target_counts = Counter((item["kind"], item["value"], item.get("name")) for item in parser.targets)
        observed = []
        for target in parser.targets:
            value = target["value"]
            if target_counts[(target["kind"], value, target.get("name"))] > 1:
                continue
            match_value = f"{value} {target.get('name', '')}"
            tokens = {token.lower() for token in re.findall(r"[\w]+", match_value) if len(token) > 2} - ignored
            overlap = len(old_tokens & tokens)
            if not overlap:
                continue
            kind = target["kind"]
            if kind == "test_id":
                selector = f"[data-testid={json.dumps(value)}]"
            elif kind == "id":
                selector = f"#{value}"
            elif kind == "name":
                selector = f"[name={json.dumps(value)}]"
            elif kind == "role":
                selector = f"role={value}[name={json.dumps(target['name'])}]"
            elif kind == "text":
                selector = f"text={json.dumps(value)}"
            elif kind == "label":
                selector = f"label={json.dumps(value)}"
            else:
                selector = f"placeholder={json.dumps(value)}"
            observed.append(
                {
                    "kind": kind,
                    "value": selector,
                    "name": target.get("name"),
                    "exact": True,
                    "evidence": f"DOM 中存在与旧定位器词项重合的 {kind} 值：{value}",
                }
            )

        ranked = rank_locator_candidates(observed)
        return [
            LocatorCandidate(
                selector=item["value"],
                strategy=item["kind"],
                confidence=round(min(0.95, item["confidence"] * 0.72 + 0.23), 2),
                reason=item["evidence"],
            )
            for item in ranked
        ]
