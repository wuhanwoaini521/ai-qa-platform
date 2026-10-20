"""Capture rules: what one structured fact is, what it may keep, and what it must never store.

These are the deterministic rules behind every number the analysis later reports, so they are
pinned here rather than inferred from a run.
"""

from __future__ import annotations

from app.services.discovery_evidence_capture import (
    DOM_ELEMENT,
    LOCATOR_CANDIDATE,
    MAX_REQUESTS_PER_STATE,
    NETWORK_REQUEST,
    SCREENSHOT,
    USER_ACTION,
    CaptureStats,
    build_action_records,
    build_state_records,
    new_requests,
    normalize_identity,
    normalize_url_template,
    resource_kind,
    stable_identity,
)


def _control(**overrides):
    control = {
        "index": 0,
        "tag": "button",
        "role": "button",
        "name": "Add to cart",
        "type": "",
        "href": "",
        "has_query": False,
        "has_credentials": False,
        "test_id": "",
        "id": "",
        "visible": True,
        "enabled": True,
        "in_viewport": True,
        "checked": False,
        "selected": False,
        "value": "",
        "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
    }
    control.update(overrides)
    return control


def _state(state_id="state_a", fingerprint="fp_a", url="http://shop.test/products?id=7"):
    return {
        "state_id": state_id,
        "fingerprint": fingerprint,
        "url": url,
        "title": "Shop",
        "depth": 1,
        "visible_controls": 3,
    }


def test_a_url_template_keeps_the_route_and_drops_the_values():
    assert normalize_url_template("http://shop.test/products?id=7&color=red") == (
        "http://shop.test/products?color=*&id=*"
    )
    assert normalize_url_template("http://shop.test/order/3f8a1c22-1111-2222-3333-444455556666") == (
        "http://shop.test/order/{uuid}"
    )
    assert normalize_url_template("http://shop.test/item/12345") == "http://shop.test/item/{n}"
    # Two servers on one host differ only by port, so the port is part of the template.
    assert normalize_url_template("http://127.0.0.1:8000/api/demo-shop/index.html") == (
        "http://127.0.0.1:8000/api/demo-shop/index.html"
    )


def test_unstable_identifiers_are_normalised_not_compared_raw():
    assert normalize_identity("card-1729") == "card-{n}"
    assert normalize_identity("sku-9f8a7b6c5d4e") == "sku-{hex}"
    # A short number is part of the name, not a counter: "Size 8" must not collapse into "Size {n}".
    assert normalize_identity("Size 8") == "Size 8"


def test_ids_are_stable_for_the_same_fact_and_different_across_facts():
    assert stable_identity("dom", "button|button|Add to cart") == stable_identity("dom", "button|button|Add to cart")
    assert stable_identity("dom", "button|button|Add to cart") != stable_identity("dom", "button|button|Checkout")


def test_a_repeated_element_is_one_fact_with_its_raw_count():
    stats = CaptureStats()

    records = build_state_records(
        _state(),
        [_control(), _control(index=1), _control(index=2), _control(index=3, name="Checkout")],
        stats,
        url="http://shop.test/products?id=7",
    )

    elements = [record for record in records if record.kind == DOM_ELEMENT]
    assert len(elements) == 2
    repeated = next(record for record in elements if record.payload["name"] == "Add to cart")
    assert repeated.payload["count_in_state"] == 3
    # raw is what the browser reported; deduped is what we kept. The gap is explainable arithmetic.
    assert stats.raw[DOM_ELEMENT] == 4
    assert stats.kept[DOM_ELEMENT] == 2


def test_an_element_with_credentials_in_its_link_is_filtered_and_counted():
    stats = CaptureStats()

    records = build_state_records(
        _state(),
        [_control(href="https://user:secret@shop.test/account", has_credentials=True), _control()],
        stats,
        url="http://shop.test/",
    )

    assert [record.payload["name"] for record in records if record.kind == DOM_ELEMENT] == ["Add to cart"]
    assert stats.filtered[f"{DOM_ELEMENT}.credentials_in_href"] == 1
    assert "secret" not in str([record.payload for record in records])


def test_input_values_are_never_stored_as_element_evidence():
    control = _control(tag="input", role="textbox", name="Email", value="buyer@example.com")

    records = build_state_records(_state(), [control], CaptureStats(), url="http://shop.test/")

    element = next(record for record in records if record.kind == DOM_ELEMENT)
    assert "value" not in element.payload
    assert "buyer@example.com" not in str(element.payload)


def test_requests_are_capped_per_state_and_the_overflow_is_reported():
    stats = CaptureStats()
    requests = [
        {"method": "GET", "url": f"http://shop.test/api/{chr(97 + index // 26)}{chr(97 + index % 26)}", "status": 200}
        for index in range(MAX_REQUESTS_PER_STATE + 5)
    ]

    records = build_state_records(_state(), [], stats, url="http://shop.test/", requests=requests)

    assert len([record for record in records if record.kind == NETWORK_REQUEST]) == MAX_REQUESTS_PER_STATE
    assert stats.raw[NETWORK_REQUEST] == MAX_REQUESTS_PER_STATE + 5
    assert stats.filtered[f"{NETWORK_REQUEST}.budget_per_state"] == 5


def test_the_same_request_twice_in_one_state_is_one_fact_with_both_statuses():
    stats = CaptureStats()
    requests = [
        {"method": "GET", "url": "http://shop.test/api/cart", "status": 200},
        {"method": "GET", "url": "http://shop.test/api/cart", "status": 500},
    ]

    records = build_state_records(_state(), [], stats, url="http://shop.test/", requests=requests)

    network = [record for record in records if record.kind == NETWORK_REQUEST]
    assert len(network) == 1
    assert network[0].payload["statuses"] == [200, 500]


def test_a_screenshot_is_referenced_by_artifact_id_never_by_bytes():
    records = build_state_records(
        _state(), [], CaptureStats(), url="http://shop.test/", screenshot_artifact_id="art_123"
    )

    shot = next(record for record in records if record.kind == SCREENSHOT)
    assert shot.artifact_id == "art_123"
    assert shot.payload == {"artifact_id": "art_123", "state_id": "state_a", "content_type": "image/png"}


def test_resources_are_classified_so_assets_do_not_inflate_behaviour_counts():
    assert resource_kind("http://shop.test/api/cart") == "api"
    assert resource_kind("http://shop.test/assets/app.js") == "asset"
    assert resource_kind("http://shop.test/") == "document"


def test_requests_between_two_observations_are_proven_by_the_list_prefix():
    before = [{"method": "GET", "url": "http://shop.test/api/items", "status": 200}]
    after = [*before, {"method": "POST", "url": "http://shop.test/api/cart", "status": 201}]

    requests, method = new_requests(before, after)

    assert method == "prefix"
    assert [request["url"] for request in requests] == ["http://shop.test/api/cart"]


def test_a_trimmed_session_log_falls_back_to_a_set_difference_instead_of_inventing_requests():
    before = [{"method": "GET", "url": "http://shop.test/api/items", "status": 200}]
    after = [
        {"method": "POST", "url": "http://shop.test/api/cart", "status": 201},
        {"method": "GET", "url": "http://shop.test/api/items", "status": 200},
    ]

    requests, method = new_requests(before, after)

    assert method == "set-difference"
    assert [request["url"] for request in requests] == ["http://shop.test/api/cart"]


def test_no_new_request_is_reported_when_nothing_arrived():
    before = [{"method": "GET", "url": "http://shop.test/api/items", "status": 200}]

    assert new_requests(before, list(before)) == ([], "none")


def test_an_action_links_its_locator_and_the_requests_it_caused():
    stats = CaptureStats()
    action = {
        "from_state_id": "state_a",
        "action_type": "click",
        "target": "Add to cart",
        "status": "EXECUTED",
        "state_changed": True,
        "to_fingerprint": "fp_b",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
    }
    candidate = {"kind": "role", "value": "button", "name": "Add to cart", "exact": True, "nth": 0}
    verification = {"match_count": 1, "unique": True, "visible": True, "verified": True}

    records = build_action_records(
        action,
        candidate,
        verification,
        stats,
        url="http://shop.test/products?id=7",
        requests=[{"method": "POST", "url": "http://shop.test/api/cart", "status": 201}],
        association="prefix",
    )

    action_record = next(record for record in records if record.kind == USER_ACTION)
    locator_record = next(record for record in records if record.kind == LOCATOR_CANDIDATE)
    network_record = next(record for record in records if record.kind == NETWORK_REQUEST)
    assert locator_record.payload["match_count"] == 1
    assert locator_record.payload["unique"] is True
    assert action_record.payload["locator_evidence_id"] == locator_record.evidence_id
    assert action_record.payload["duration_ms"] == 1000.0
    assert action_record.payload["network_association"] == "prefix"
    assert network_record.payload["action_evidence_id"] == action_record.evidence_id
    assert action_record.payload["network_evidence_ids"] == [network_record.evidence_id]
    assert stats.kept[USER_ACTION] == 1 and stats.kept[LOCATOR_CANDIDATE] == 1


def test_rebuilding_the_same_action_yields_the_same_ids():
    action = {"from_state_id": "state_a", "action_type": "click", "target": "Add to cart", "to_fingerprint": "fp_b"}
    candidate = {"kind": "role", "value": "button", "name": "Add to cart"}

    first = build_action_records(action, candidate, None, CaptureStats(), url="http://shop.test/")
    second = build_action_records(action, candidate, None, CaptureStats(), url="http://shop.test/")

    assert [record.evidence_id for record in first] == [record.evidence_id for record in second]


def test_a_page_state_record_carries_the_fingerprint_the_diff_compares():
    records = build_state_records(_state(), [], CaptureStats(), url="http://shop.test/products?id=7")

    page = next(record for record in records if record.kind == "page_state")
    assert page.payload["fingerprint"] == "fp_a"
    assert page.payload["url_template"] == "http://shop.test/products?id=*"
    assert page.state_id == "state_a"


def test_a_discovery_candidate_carries_the_locator_it_nests():
    # Discovery candidates keep the locator under `locator`; reading the flat keys left it empty.
    action = {"from_state_id": "state_a", "action_type": "click", "target": "View health"}
    candidate = {
        "candidate_id": "cand_1",
        "action_type": "click",
        "target": "View health",
        "locator": {"kind": "role", "value": "button", "name": "View health", "exact": True},
    }
    verification = {"match_count": 1, "unique": True, "visible": True, "verified": True}

    records = build_action_records(
        action,
        candidate,
        verification,
        CaptureStats(),
        url="http://shop.test/discovery-fixture.html",
        requests=[],
    )

    locator_record = next(record for record in records if record.kind == LOCATOR_CANDIDATE)
    assert locator_record.payload["kind"] == "role"
    assert locator_record.payload["value"] == "button"
    assert locator_record.payload["name"] == "View health"
    assert locator_record.payload["match_count"] == 1
    assert locator_record.payload["page"] == "http://shop.test/discovery-fixture.html"
