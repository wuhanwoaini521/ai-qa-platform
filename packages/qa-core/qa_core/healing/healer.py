from __future__ import annotations

import re

from qa_core.healing.models import LocatorCandidate, LocatorRepairProposal


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
        candidates = cls._generate_candidates(old_locator, dom_snapshot)
        best = (
            candidates[0]
            if candidates
            else LocatorCandidate(
                selector=old_locator,
                strategy="fallback",
                confidence=0.5,
                reason="No confident DOM replacement identified.",
            )
        )

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
        candidates: list[LocatorCandidate] = []

        # 1. Semantic data-testid fallback
        clean_name = re.sub(r"[#\.\-_\[\]=]", " ", old_locator).strip().split()
        tag = clean_name[-1] if clean_name else "element"

        candidates.append(
            LocatorCandidate(
                selector=f'[data-testid="{tag}"]',
                strategy="semantic-attribute",
                confidence=0.92,
                reason=f"Standard semantic attribute fallback for target '{tag}'.",
            )
        )

        # 2. Text / Role fallback
        candidates.append(
            LocatorCandidate(
                selector=f'button:has-text("{tag.capitalize()}")'
                if "btn" in old_locator or "button" in old_locator
                else f'text="{tag.capitalize()}"',
                strategy="role-and-text",
                confidence=0.85,
                reason=f"User-facing visible text target for '{tag}'.",
            )
        )

        return candidates
