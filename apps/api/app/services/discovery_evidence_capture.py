"""Turn what the browser already observed into structured, addressable evidence.

The run row keeps a compact JSON projection; this module is the deterministic side that decides
what one fact *is* (its stable id and its dedupe key), what it may keep (budgets and redaction)
and how a request is tied to the action that caused it. It never calls a model: every number in
the analysis later comes from these records.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DOM_ELEMENT = "dom_element"
LOCATOR_CANDIDATE = "locator_candidate"
NETWORK_REQUEST = "network_request"
USER_ACTION = "user_action"
PAGE_STATE = "page_state"
SCREENSHOT = "screenshot"

KINDS = (DOM_ELEMENT, LOCATOR_CANDIDATE, NETWORK_REQUEST, USER_ACTION, PAGE_STATE, SCREENSHOT)

#: One state contributes at most this many element rows; the rest is reported, never dropped silently.
MAX_ELEMENTS_PER_STATE = 60
#: Requests kept per state and per action, so a polling page cannot flood the index.
MAX_REQUESTS_PER_STATE = 40
_ASSET_SUFFIXES = (
    ".js",
    ".mjs",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".ico",
    ".map",
)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_DIGITS = re.compile(r"\d{2,}")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def stable_identity(prefix: str, key: str) -> str:
    """A readable id that stays the same for the same fact across runs of the same evidence kind."""
    return f"{prefix}_{_digest(key)}"


def normalize_identity(value: str) -> str:
    """Erase the parts of an identifier that change between page loads (uuid, hash, counter)."""
    text = str(value or "")
    text = _UUID.sub("{uuid}", text)
    text = _HEX.sub("{hex}", text)
    return _DIGITS.sub("{n}", text)


def normalize_url_template(url: str) -> str:
    """Keep the route, drop the query values: ``/product?id=7`` becomes ``/product?id=*``."""
    try:
        parts = urlsplit(str(url or ""))
    except ValueError:
        return ""
    query_keys = sorted({f"{key}=*" for key in (item.split("=", 1)[0] for item in parts.query.split("&") if item)})
    path = normalize_identity(parts.path)
    # The port stays in the template: 127.0.0.1:8000 and 127.0.0.1:5173 are different servers.
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, path, "&".join(query_keys), ""))


def resource_kind(url: str) -> str:
    """Classify by suffix and path, which is what decides whether a request says anything about behaviour."""
    path = urlsplit(str(url or "")).path.lower()
    last = path.rsplit("/", 1)[-1]
    if "." not in last:
        # An extension-less path is a page unless it sits under an api segment: /api/cart is a call,
        # /products is a navigation.
        return "api" if "api" in [segment for segment in path.split("/") if segment] else "document"
    if path.endswith((".html", ".htm")):
        return "document"
    for suffix in _ASSET_SUFFIXES:
        if path.endswith(suffix):
            return "asset"
    return "api"


@dataclass(frozen=True)
class EvidenceRecord:
    kind: str
    evidence_id: str
    dedupe_key: str
    payload: dict[str, Any]
    state_id: str | None = None
    step_id: str | None = None
    artifact_id: str | None = None
    source: str = "browser_runtime"


@dataclass
class CaptureStats:
    """Raw vs kept counts per kind — the four numbers the analysis must not guess."""

    raw: dict[str, int] = field(default_factory=dict)
    kept: dict[str, int] = field(default_factory=dict)
    filtered: dict[str, int] = field(default_factory=dict)

    def seen(self, kind: str, count: int = 1) -> None:
        self.raw[kind] = self.raw.get(kind, 0) + count

    def keep(self, kind: str, count: int = 1) -> None:
        self.kept[kind] = self.kept.get(kind, 0) + count

    def drop(self, kind: str, reason: str, count: int = 1) -> None:
        key = f"{kind}.{reason}"
        self.filtered[key] = self.filtered.get(key, 0) + count

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": dict(sorted(self.raw.items())),
            "kept": dict(sorted(self.kept.items())),
            "filtered": dict(sorted(self.filtered.items())),
        }


def element_key(control: dict[str, Any]) -> str:
    """Identity of an element across states: structure and wording, not layout or values."""
    return "|".join(
        [
            str(control.get("tag") or ""),
            str(control.get("role") or ""),
            str(control.get("name") or ""),
            str(control.get("test_id") or ""),
            normalize_identity(str(control.get("id") or "")),
            normalize_identity(str(control.get("href") or "")),
        ]
    )


def _element_payload(control: dict[str, Any], state_id: str, url: str, count_in_state: int) -> dict[str, Any]:
    return {
        "tag": control.get("tag"),
        "role": control.get("role"),
        "name": control.get("name"),
        "type": control.get("type"),
        "test_id": control.get("test_id") or None,
        "element_id": control.get("id") or None,
        "href_template": normalize_url_template(str(control.get("href") or "")),
        "in_viewport": bool(control.get("in_viewport")),
        "enabled": bool(control.get("enabled", True)),
        "checked": bool(control.get("checked")),
        "selected": bool(control.get("selected")),
        #: How many controls in this state share this identity — the raw count behind the dedupe.
        "count_in_state": count_in_state,
        "state_id": state_id,
        "page": normalize_url_template(url),
    }


def _locator_of(candidate: dict[str, Any]) -> dict[str, Any]:
    """A discovery candidate nests its locator; a recorder candidate carries it flat."""
    nested = candidate.get("locator")
    return nested if isinstance(nested, dict) and nested else candidate


def _locator_payload(candidate: dict[str, Any], verification: dict[str, Any] | None, url: str) -> dict[str, Any]:
    locator = _locator_of(candidate)
    return {
        "kind": locator.get("kind"),
        "value": str(locator.get("value") or ""),
        "name": locator.get("name"),
        "exact": bool(locator.get("exact", True)),
        "nth": locator.get("nth"),
        "match_count": (verification or {}).get("match_count"),
        "unique": (verification or {}).get("unique"),
        "visible": (verification or {}).get("visible"),
        "verified": (verification or {}).get("verified"),
        "page": normalize_url_template(url),
    }


def locator_key(candidate: dict[str, Any]) -> str:
    locator = _locator_of(candidate)
    return "|".join(
        [
            str(locator.get("kind") or ""),
            str(locator.get("value") or ""),
            str(locator.get("name") or ""),
            str(bool(locator.get("exact", True))),
            str(locator.get("nth")),
        ]
    )


def _network_payload(item: dict[str, Any], state_id: str, action_evidence_id: str | None) -> dict[str, Any]:
    return {
        "method": str(item.get("method") or "GET").upper(),
        "url_template": normalize_url_template(str(item.get("url") or "")),
        "resource": resource_kind(str(item.get("url") or "")),
        "statuses": [int(item["status"])] if item.get("status") is not None else [],
        "failed": bool(item.get("failed")),
        "state_id": state_id,
        "action_evidence_id": action_evidence_id,
    }


def network_key(item: dict[str, Any]) -> str:
    return f"{str(item.get('method') or 'GET').upper()}|{normalize_url_template(str(item.get('url') or ''))}"


def _merge_network(record: EvidenceRecord, item: dict[str, Any]) -> EvidenceRecord:
    payload = dict(record.payload)
    statuses = list(payload.get("statuses") or [])
    status = item.get("status")
    if status is not None and int(status) not in statuses:
        statuses.append(int(status))
    payload["statuses"] = sorted(statuses)[:10]
    payload["failed"] = bool(payload.get("failed")) or bool(item.get("failed"))
    if payload.get("action_evidence_id") is None:
        payload["action_evidence_id"] = None
    return EvidenceRecord(
        kind=record.kind,
        evidence_id=record.evidence_id,
        dedupe_key=record.dedupe_key,
        payload=payload,
        state_id=record.state_id,
        artifact_id=record.artifact_id,
        source=record.source,
    )


def network_keys(requests: list[dict[str, Any]]) -> list[str]:
    return [network_key(item) for item in requests]


def new_requests(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Requests that arrived during an action, and which rule proved it.

    The browser session keeps one cumulative list, so the honest answer is a prefix comparison.
    When the session trimmed its list the prefix no longer matches and we fall back to a set
    difference, which is over-inclusive but never invents a request.
    """
    if len(after) <= len(before):
        return [], "none"
    prefix = after[: len(before)]
    if [network_key(item) for item in prefix] == [network_key(item) for item in before]:
        return after[len(before) :], "prefix"
    seen = {network_key(item) for item in before}
    return [item for item in after if network_key(item) not in seen], "set-difference"


def build_state_records(
    state: dict[str, Any],
    controls: list[dict[str, Any]],
    stats: CaptureStats,
    *,
    url: str,
    requests: list[dict[str, Any]] | None = None,
    screenshot_artifact_id: str | None = None,
) -> list[EvidenceRecord]:
    """Element, network and page-state evidence for one observed state."""
    state_id = str(state.get("state_id") or "")
    page = EvidenceRecord(
        kind=PAGE_STATE,
        evidence_id=f"state_{state_id}",
        dedupe_key=f"{state_id}|{state.get('fingerprint')}",
        state_id=state_id,
        step_id=state_id,
        payload={
            "state_id": state_id,
            "fingerprint": state.get("fingerprint"),
            "url": state.get("url"),
            "url_template": normalize_url_template(str(state.get("url") or "")),
            "title": state.get("title"),
            "depth": state.get("depth"),
            "visible_controls": state.get("visible_controls"),
            "controls_total": len(controls),
        },
    )
    records: list[EvidenceRecord] = []

    groups: dict[str, list[dict[str, Any]]] = {}
    for control in controls:
        stats.seen(DOM_ELEMENT)
        if control.get("has_credentials"):
            stats.drop(DOM_ELEMENT, "credentials_in_href")
            continue
        groups.setdefault(element_key(control), []).append(control)
    for key, group in groups.items():
        first = group[0]
        records.append(
            EvidenceRecord(
                kind=DOM_ELEMENT,
                evidence_id=stable_identity("dom", key),
                dedupe_key=key,
                state_id=state_id,
                step_id=state_id,
                payload=_element_payload(first, state_id, url, len(group)),
            )
        )
        stats.keep(DOM_ELEMENT)

    merged: dict[str, EvidenceRecord] = {}
    for item in requests or []:
        stats.seen(NETWORK_REQUEST)
        if not item.get("url"):
            stats.drop(NETWORK_REQUEST, "missing_url")
            continue
        key = network_key(item)
        existing = merged.get(key)
        if existing is not None:
            merged[key] = _merge_network(existing, item)
            continue
        if len(merged) >= MAX_REQUESTS_PER_STATE:
            stats.drop(NETWORK_REQUEST, "budget_per_state")
            continue
        merged[key] = EvidenceRecord(
            kind=NETWORK_REQUEST,
            evidence_id=stable_identity("net", key),
            dedupe_key=key,
            state_id=state_id,
            step_id=state_id,
            payload=_network_payload(item, state_id, None),
        )
        stats.keep(NETWORK_REQUEST)
    records.extend(merged.values())

    if screenshot_artifact_id:
        records.append(
            EvidenceRecord(
                kind=SCREENSHOT,
                evidence_id=f"shot_{screenshot_artifact_id}",
                dedupe_key=f"{state_id}|{screenshot_artifact_id}",
                state_id=state_id,
                step_id=state_id,
                artifact_id=screenshot_artifact_id,
                payload={"artifact_id": screenshot_artifact_id, "state_id": state_id, "content_type": "image/png"},
            )
        )
    return [page, *records]


def build_action_records(
    action: dict[str, Any],
    candidate: dict[str, Any],
    verification: dict[str, Any] | None,
    stats: CaptureStats,
    *,
    url: str,
    requests: list[dict[str, Any]] | None = None,
    association: str = "none",
    element_control: dict[str, Any] | None = None,
) -> list[EvidenceRecord]:
    """User action, its locator candidate and the requests that arrived while it ran.

    ``element_control`` is the control the action targeted; the element evidence id is only
    linked when that control was captured, so a reference never dangles.
    """
    from_state = str(action.get("from_state_id") or "")
    locator_key_value = locator_key(candidate)
    action_key = "|".join(
        [
            from_state,
            str(action.get("action_type") or ""),
            locator_key_value,
            str(action.get("to_fingerprint") or ""),
        ]
    )
    action_evidence_id = stable_identity("act", action_key)
    records: list[EvidenceRecord] = []

    stats.seen(LOCATOR_CANDIDATE)
    payload = _locator_payload(candidate, verification, url)
    payload["element_evidence_id"] = stable_identity("dom", element_key(element_control)) if element_control else None
    records.append(
        EvidenceRecord(
            kind=LOCATOR_CANDIDATE,
            evidence_id=stable_identity("loc", locator_key_value),
            dedupe_key=locator_key_value,
            state_id=from_state,
            step_id=action_evidence_id,
            payload=payload,
        )
    )
    stats.keep(LOCATOR_CANDIDATE)

    stats.seen(USER_ACTION)
    records.append(
        EvidenceRecord(
            kind=USER_ACTION,
            evidence_id=action_evidence_id,
            dedupe_key=action_key,
            state_id=from_state,
            step_id=action_evidence_id,
            payload={
                "action": action.get("action_type"),
                "target": action.get("target"),
                "status": action.get("status"),
                "state_changed": bool(action.get("state_changed")),
                "from_state_id": from_state,
                "to_fingerprint": action.get("to_fingerprint"),
                "duration_ms": _duration_ms(action),
                "locator_evidence_id": stable_identity("loc", locator_key_value),
                "element_evidence_id": payload["element_evidence_id"],
                "match_count": (verification or {}).get("match_count"),
                "unique": (verification or {}).get("unique"),
                "network_association": association,
                "network_evidence_ids": [],
            },
        )
    )
    stats.keep(USER_ACTION)

    network_ids: list[str] = []
    for item in requests or []:
        stats.seen(NETWORK_REQUEST)
        if not item.get("url"):
            stats.drop(NETWORK_REQUEST, "missing_url")
            continue
        key = network_key(item)
        evidence_id = stable_identity("net", key)
        network_ids.append(evidence_id)
        records.append(
            EvidenceRecord(
                kind=NETWORK_REQUEST,
                evidence_id=evidence_id,
                dedupe_key=key,
                state_id=from_state,
                step_id=action_evidence_id,
                payload=_network_payload(item, from_state, action_evidence_id),
            )
        )
        stats.keep(NETWORK_REQUEST)
    if network_ids:
        action_record = records[1]
        payload = dict(action_record.payload)
        payload["network_evidence_ids"] = sorted(set(network_ids))
        records[1] = EvidenceRecord(
            kind=action_record.kind,
            evidence_id=action_record.evidence_id,
            dedupe_key=action_record.dedupe_key,
            payload=payload,
            state_id=action_record.state_id,
            step_id=action_record.step_id,
        )
    return records


def _duration_ms(action: dict[str, Any]) -> float | None:
    started = action.get("started_at")
    finished = action.get("finished_at")
    if not started or not finished:
        return None
    try:
        from datetime import datetime

        start = datetime.fromisoformat(str(started))
        end = datetime.fromisoformat(str(finished))
        return round((end - start).total_seconds() * 1000, 1)
    except ValueError:
        return None
