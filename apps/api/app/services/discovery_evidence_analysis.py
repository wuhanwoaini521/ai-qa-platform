"""Deterministic analysis over captured discovery evidence.

Everything here is arithmetic over stored rows: counts with a stated denominator, locator
uniqueness, request/action association, candidate scenarios matched against existing test cases,
and a run-to-run diff that reports a missing capture as *missing* instead of "everything vanished".
No model is consulted, so the same rows always produce the same numbers.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from app.persistence.models import DiscoveryEvidenceORM, DiscoveryScenarioORM
from app.services.discovery_evidence_capture import (
    DOM_ELEMENT,
    LOCATOR_CANDIDATE,
    NETWORK_REQUEST,
    PAGE_STATE,
    SCREENSHOT,
    USER_ACTION,
    normalize_identity,
    stable_identity,
)

COVERED = "COVERED"
CANDIDATE_GAP = "CANDIDATE_GAP"
UNDETERMINED = "UNDETERMINED"

#: A target shorter than this cannot prove coverage on its own: "Add" appears in half a suite.
MIN_TARGET_CHARS = 4

#: Locator values that name a control kind rather than a control. They match everything.
GENERIC_LOCATOR_VALUES = frozenset(
    {
        "a",
        "button",
        "checkbox",
        "combobox",
        "div",
        "input",
        "link",
        "listbox",
        "menuitem",
        "radio",
        "searchbox",
        "select",
        "slider",
        "span",
        "spinbutton",
        "tab",
        "textbox",
        "textarea",
    }
)
_WORD = re.compile(r"[a-z0-9\u4e00-\u9fff]{2,}", re.I)


def evidence_kind_facts(kind: str, payload: dict[str, Any]) -> str:
    """One plain-language line about a captured fact, shared by the prompt and the API."""
    if kind == "dom_element":
        return (
            f"tag={payload.get('tag')} role={payload.get('role') or '-'} "
            f"name={payload.get('name')!r} count_in_state={payload.get('count_in_state')} "
            f"enabled={payload.get('enabled')}"
        )
    if kind == "locator_candidate":
        return (
            f"locator={payload.get('locator_value')!r} kind={payload.get('kind')} "
            f"match_count={payload.get('match_count')} unique={payload.get('unique')} verified={payload.get('verified')}"
        )
    if kind == "network_request":
        return (
            f"{payload.get('method')} {payload.get('url_template')} statuses={payload.get('statuses')} "
            f"resource={payload.get('resource')}"
        )
    if kind == "user_action":
        return (
            f"{payload.get('action')} target={payload.get('target')!r} status={payload.get('status')} "
            f"state_changed={payload.get('state_changed')} requests={payload.get('network_evidence_ids')}"
        )
    if kind == "page_state":
        return (
            f"url_template={payload.get('url_template')} visible_controls={payload.get('visible_controls')} "
            f"fingerprint={payload.get('fingerprint')}"
        )
    if kind == "screenshot":
        return f"artifact={payload.get('artifact_id')} url_template={payload.get('url_template')}"
    return str(payload)


def _row_payload(row: DiscoveryEvidenceORM) -> dict[str, Any]:
    return dict(row.payload or {})


def _capture_totals(states: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Sum the per-state capture counters: the raw numbers behind the dedupe."""
    raw: dict[str, int] = {}
    kept: dict[str, int] = {}
    filtered: dict[str, int] = {}
    for state in states:
        capture = state.get("capture") if isinstance(state, dict) else None
        if not isinstance(capture, dict):
            continue
        for key, value in (capture.get("raw") or {}).items():
            raw[key] = raw.get(key, 0) + int(value)
        for key, value in (capture.get("kept") or {}).items():
            kept[key] = kept.get(key, 0) + int(value)
        for key, value in (capture.get("filtered") or {}).items():
            filtered[key] = filtered.get(key, 0) + int(value)
    return {"raw": raw, "kept": kept, "filtered": filtered}


#: Every number this module reports says which rule produced it, so no consumer has to guess.
MEASURES = {
    "dom_element.raw": "controls the browser reported per state, before any dedupe",
    "dom_element.deduped": (
        "distinct element identities (tag|role|name|test id|stable id|stable href) over all states"
    ),
    "dom_element.filtered": ("dropped on purpose: unstable links, credentials in the href, or the per-state budget"),
    "network_request.raw": "responses the browser observed per state",
    "network_request.deduped": "distinct method + url-template pairs per state",
    "network_request.associated": "requests proven to follow an action by the response-list prefix or set difference",
    "network_request.unassociated": "requests no action could be tied to — reported, never assumed",
    "locator_candidate.ambiguous": "locators whose verified match count is greater than one",
    "user_action.state_changed": "actions whose page fingerprint differs from the state they started in",
    "page_state.total": "distinct page states reached",
    "screenshot.total": "screenshots referenced by artifact id; binaries are never copied here",
    "state_captures": "states that actually stored capture counters",
}


def _kind_counts(rows: Sequence[DiscoveryEvidenceORM]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.kind] = counts.get(row.kind, 0) + 1
    return {kind: counts[kind] for kind in sorted(counts)}


def analyze_collection(
    rows: Sequence[DiscoveryEvidenceORM], states: Sequence[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The collection half of the picture: what was captured, deduped, filtered and associated."""
    totals = _capture_totals(states or [])
    stored = _kind_counts(rows)
    raw = totals["raw"]
    filtered = totals["filtered"]

    def filtered_for(kind: str) -> int:
        return sum(count for key, count in filtered.items() if key.split(".", 1)[0] == kind)

    elements = [row for row in rows if row.kind == DOM_ELEMENT]
    requests = [row for row in rows if row.kind == NETWORK_REQUEST]
    actions = [row for row in rows if row.kind == USER_ACTION]
    locators = [row for row in rows if row.kind == LOCATOR_CANDIDATE]
    pages = [row for row in rows if row.kind == PAGE_STATE]

    resource_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for row in requests:
        payload = _row_payload(row)
        resource = str(payload.get("resource") or "unknown")
        resource_counts[resource] = resource_counts.get(resource, 0) + 1
        for status in payload.get("statuses") or []:
            bucket = f"{int(status) // 100}xx"
            status_counts[bucket] = status_counts.get(bucket, 0) + 1

    associated = [row for row in requests if _row_payload(row).get("action_evidence_id")]
    methods: dict[str, int] = {}
    for row in requests:
        payload = _row_payload(row)
        if payload.get("action_evidence_id"):
            from_action = next((item for item in actions if item.evidence_id == payload["action_evidence_id"]), None)
            method = str(_row_payload(from_action).get("network_association") or "unknown") if from_action else "orphan"
            methods[method] = methods.get(method, 0) + 1

    unique_locators = [row for row in locators if _row_payload(row).get("unique")]
    verified_locators = [row for row in locators if _row_payload(row).get("verified")]
    duplicate_locators = [row for row in locators if int(_row_payload(row).get("match_count") or 0) > 1]
    state_changes = [row for row in actions if _row_payload(row).get("state_changed")]

    return {
        # raw = everything the browser reported; deduped = distinct facts kept; filtered = dropped on purpose.
        "dom_element": {
            "raw": raw.get(DOM_ELEMENT, len(elements)),
            "deduped": len(elements),
            "filtered": filtered_for(DOM_ELEMENT),
            "stored": stored.get(DOM_ELEMENT, 0),
        },
        "network_request": {
            "raw": raw.get(NETWORK_REQUEST, len(requests)),
            "deduped": len(requests),
            "filtered": filtered_for(NETWORK_REQUEST),
            "stored": stored.get(NETWORK_REQUEST, 0),
            "by_resource": dict(sorted(resource_counts.items())),
            "by_status": dict(sorted(status_counts.items())),
            "associated": len(associated),
            "unassociated": len(requests) - len(associated),
            "association_methods": dict(sorted(methods.items())),
        },
        "locator_candidate": {
            "total": len(locators),
            "unique": len(unique_locators),
            "verified": len(verified_locators),
            "ambiguous": len(duplicate_locators),
            "ambiguous_evidence_ids": sorted(row.evidence_id for row in duplicate_locators)[:20],
        },
        "user_action": {
            "total": len(actions),
            "state_changed": len(state_changes),
            "no_state_change": len(actions) - len(state_changes),
            "with_requests": sum(1 for row in actions if _row_payload(row).get("network_evidence_ids")),
        },
        "page_state": {
            "total": len(pages),
            "fingerprints": sorted({str(_row_payload(row).get("fingerprint")) for row in pages}),
        },
        "screenshot": {"total": stored.get(SCREENSHOT, 0)},
        "filtered_breakdown": dict(sorted(filtered.items())),
        "state_captures": sum(1 for state in states or [] if isinstance(state, dict) and state.get("capture")),
        "measures": dict(MEASURES),
    }


def _tokens(text: str) -> set[str]:
    return {token for token in _WORD.findall(normalize_identity(text).lower()) if len(token) >= 2}


def _test_corpus(case: dict[str, Any]) -> str:
    parts = [
        str(case.get("title") or ""),
        " ".join(str(step) for step in case.get("steps") or []),
        str(case.get("expected_result") or ""),
        str(case.get("preconditions") or ""),
        " ".join(str(tag) for tag in case.get("tags") or []),
        str((case.get("binding") or {}).get("file_path") or ""),
        str((case.get("binding") or {}).get("test_name") or ""),
    ]
    return " ".join(parts).lower()


def build_scenarios(rows: Sequence[DiscoveryEvidenceORM]) -> list[dict[str, Any]]:
    """One candidate scenario per distinct action on a page, carrying the evidence that proved it."""
    actions = [row for row in rows if row.kind == USER_ACTION]
    pages = {str(_row_payload(row).get("state_id")): _row_payload(row) for row in rows if row.kind == PAGE_STATE}
    scenarios: dict[str, dict[str, Any]] = {}
    for row in actions:
        payload = _row_payload(row)
        state_id = str(payload.get("from_state_id") or "")
        page = pages.get(state_id) or {}
        url_template = str(page.get("url_template") or "")
        action = str(payload.get("action") or "")
        target = str(payload.get("target") or "")
        key = f"{url_template}|{action}|{normalize_identity(target)}"
        scenario_id = stable_identity("scen", key)
        evidence_ids = sorted(
            {
                evidence_id
                for evidence_id in (
                    row.evidence_id,
                    payload.get("locator_evidence_id"),
                    payload.get("element_evidence_id"),
                    *(payload.get("network_evidence_ids") or []),
                )
                if evidence_id
            }
        )
        existing = scenarios.get(scenario_id)
        if existing:
            existing["evidence_ids"] = sorted({*existing["evidence_ids"], *evidence_ids})
            existing["actions"] += 1
            continue
        scenarios[scenario_id] = {
            "scenario_id": scenario_id,
            "title": f"{action} {target}".strip()[:300],
            "url_template": url_template[:600],
            "evidence_ids": evidence_ids,
            "action": action,
            "target": target,
            "locator_value": _locator_value(rows, payload),
            "state_changed": bool(payload.get("state_changed")),
            "actions": 1,
        }
    return [scenarios[key] for key in sorted(scenarios)]


def _locator_value(rows: Sequence[DiscoveryEvidenceORM], action_payload: dict[str, Any]) -> str:
    locator_id = action_payload.get("locator_evidence_id")
    if not locator_id:
        return ""
    for row in rows:
        if row.kind == LOCATOR_CANDIDATE and row.evidence_id == locator_id:
            payload = _row_payload(row)
            value = str(payload.get("value") or "")
            # A role locator's value is just the element kind (`button`), which appears in almost every
            # test case and would fake coverage; the accessible name is what identifies the element.
            if value.lower() in GENERIC_LOCATOR_VALUES:
                return str(payload.get("name") or "")
            return value
    return ""


def match_scenarios(scenarios: Sequence[dict[str, Any]], cases: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the existing test cases a scenario is provably about, and say how we know.

    COVERED needs a concrete hit (the locator value, or the target wording in the case text).
    A scenario whose target is too generic to prove anything stays UNDETERMINED; everything else
    is a CANDIDATE_GAP — a candidate, because a human or a later model-assisted round confirms it.
    """
    corpora = [(str(case.get("id") or ""), _test_corpus(case)) for case in cases]
    matched: list[dict[str, Any]] = []
    for scenario in scenarios:
        target = str(scenario.get("target") or "")
        locator_value = str(scenario.get("locator_value") or "")
        target_tokens = _tokens(target)
        hits: list[str] = []
        method: str | None = None
        if len(locator_value) >= MIN_TARGET_CHARS:
            for case_id, corpus in corpora:
                if locator_value.lower() in corpus:
                    hits.append(case_id)
            if hits:
                method = "locator_value"
        if not hits and len(target_tokens) >= 2:
            for case_id, corpus in corpora:
                corpus_tokens = _tokens(corpus)
                if target_tokens and len(target_tokens & corpus_tokens) / len(target_tokens) >= 0.75:
                    hits.append(case_id)
            if hits:
                method = "target_wording"
        if hits:
            status = COVERED
            note = f"Matched {len(hits)} existing case(s) by {method}."
        elif len(target) < MIN_TARGET_CHARS or not target_tokens:
            status = UNDETERMINED
            note = "The observed target is too generic to prove or disprove coverage; needs a human or model review."
        else:
            status = CANDIDATE_GAP
            note = "No existing test case references this behaviour; treated as a candidate gap."
        matched.append(
            {
                **scenario,
                "test_case_ids": sorted(set(hits))[:20],
                "coverage_status": status,
                "match_method": method,
                "note": note,
            }
        )
    return matched


def coverage_summary(scenarios: Sequence[DiscoveryScenarioORM | dict[str, Any]]) -> dict[str, Any]:
    counts = {COVERED: 0, CANDIDATE_GAP: 0, UNDETERMINED: 0}
    for scenario in scenarios:
        status = (
            scenario.coverage_status if isinstance(scenario, DiscoveryScenarioORM) else scenario.get("coverage_status")
        )
        counts[str(status)] = counts.get(str(status), 0) + 1
    return {
        "total": len(scenarios),
        **counts,
        # Stated explicitly so nobody reads "covered / total" as business coverage.
        "measures": "observed UI behaviour reported by this run, matched against existing test case text",
    }


def diff_runs(
    current: Sequence[DiscoveryEvidenceORM],
    previous: Sequence[DiscoveryEvidenceORM] | None,
    *,
    current_run_id: str,
    previous_run_id: str | None,
) -> dict[str, Any]:
    """Compare two runs of the same scope by stable dedupe keys, per kind."""
    if not previous:
        return {
            "current_run_id": current_run_id,
            "previous_run_id": previous_run_id,
            "comparable": False,
            "reason": "previous_run_has_no_captured_evidence",
            "kinds": {},
        }
    kinds = [DOM_ELEMENT, NETWORK_REQUEST, PAGE_STATE, USER_ACTION]
    current_keys = {(row.kind, row.dedupe_key): row for row in current}
    previous_keys = {(row.kind, row.dedupe_key): row for row in previous}
    result: dict[str, Any] = {
        "current_run_id": current_run_id,
        "previous_run_id": previous_run_id,
        "comparable": True,
        "kinds": {},
    }
    for kind in kinds:
        before = {key: row for (row_kind, key), row in previous_keys.items() if row_kind == kind}
        after = {key: row for (row_kind, key), row in current_keys.items() if row_kind == kind}
        if not before and not after:
            result["kinds"][kind] = {"comparable": False, "reason": "neither_run_captured_this_kind"}
            continue
        if not before:
            result["kinds"][kind] = {
                "comparable": False,
                "reason": "previous_run_captured_nothing_of_this_kind",
                "added": len(after),
            }
            continue
        if not after:
            result["kinds"][kind] = {
                "comparable": False,
                "reason": "current_run_captured_nothing_of_this_kind",
                "removed": len(before),
            }
            continue
        added = sorted(key for key in after if key not in before)
        removed = sorted(key for key in before if key not in after)
        changed: list[dict[str, Any]] = []
        for key in sorted(set(before) & set(after)):
            before_payload = _row_payload(before[key])
            after_payload = _row_payload(after[key])
            if kind == NETWORK_REQUEST:
                if sorted(before_payload.get("statuses") or []) != sorted(after_payload.get("statuses") or []):
                    changed.append(
                        {
                            "dedupe_key": key,
                            "before": {"statuses": before_payload.get("statuses")},
                            "after": {"statuses": after_payload.get("statuses")},
                        }
                    )
            elif kind == PAGE_STATE:
                if before_payload.get("url_template") != after_payload.get("url_template"):
                    changed.append(
                        {
                            "dedupe_key": key,
                            "before": {"url_template": before_payload.get("url_template")},
                            "after": {"url_template": after_payload.get("url_template")},
                        }
                    )
        result["kinds"][kind] = {
            "comparable": True,
            "previous": len(before),
            "current": len(after),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "added_keys": added[:20],
            "removed_keys": removed[:20],
            "changed_items": changed[:20],
        }
    return result
