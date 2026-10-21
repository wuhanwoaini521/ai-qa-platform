"""Round 21 measurement harness: real UI at four viewports, plus a stubbed-scale stress run.

Two kinds of numbers, kept apart on purpose:

1. `real` — the product surfaces loaded from the running dev stack with the project's actual records:
   first contentful paint, DOM size, canvas node count and zoom, interaction latency, console errors.
2. `stress` — the *same* ExecutionTreePanel component with `/execution-trace` responses replaced by
   synthetic payloads of 100/500/1000 nodes. Only the server data is synthetic; React Flow, the layout,
   the cards and the CSS are the real ones. This is the only way to measure beyond the product's own
   limits (a definition holds at most 30 nodes, a project trace aggregates 6 tasks).

Run: cd <repo> && uv run python .ai-runs/overnight-delivery/rounds/r21_perf.py [before|after]
Writes .ai-runs/overnight-delivery/rounds/r21-perf-<phase>.json and screenshots under rounds/screenshots/.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time

from playwright.async_api import async_playwright

ROOT = pathlib.Path(".").resolve()
OUT = ROOT / ".ai-runs/overnight-delivery/rounds"
SHOTS = OUT / "screenshots"
WEB = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"
PROJECT = "proj_golden_shop_v1"
VIEWPORTS = {"w1560": 1560, "w1280": 1280, "w1024": 1024, "w390": 390}
MEDIA = {"w1560": 1560, "w1280": 1280, "w1024": 1024, "w390": 390}

results: dict[str, object] = {"real": {}, "stress": {}, "console": []}


async def login(page) -> str:
    await page.goto(f"{WEB}/login", wait_until="domcontentloaded")
    await page.fill("#login-email", "admin@ai-qa.local")
    await page.fill("#login-password", "adminpassword")
    await page.click("button[type=submit]")
    await page.wait_for_function("() => Boolean(localStorage.getItem('ai-qa.auth-token'))", timeout=30000)
    return await page.evaluate("() => localStorage.getItem('ai-qa.auth-token')")


def canvas_url(mode: str) -> str:
    return f"{WEB}/workspace/{PROJECT}?projectId={PROJECT}&stage=automation&view=canvas&canvas={mode}"


async def measure(page) -> dict:
    """Numbers the browser can give us honestly: paint, DOM weight, canvas geometry, zoom."""
    return await page.evaluate(
        """() => {
            const nav = performance.getEntriesByType('navigation')[0];
            const paints = performance.getEntriesByType('paint');
            const fcp = paints.find((entry) => entry.name === 'first-contentful-paint');
            const cards = document.querySelectorAll('.react-flow__node');
            const viewport = document.querySelector('.react-flow__viewport');
            const zoom = viewport ? new DOMMatrixReadOnly(getComputedStyle(viewport).transform).a : null;
            const scale = zoom === null ? 1 : zoom;
            const smallest = Array.from(cards).reduce((worst, card) => {
                const parts = card.querySelectorAll('strong, span');
                return Array.from(parts).reduce((inner, part) => {
                    const size = parseFloat(getComputedStyle(part).fontSize) * scale;
                    return size > 0 && size < inner ? size : inner;
                }, worst);
            }, Number.POSITIVE_INFINITY);
            const tiny = Array.from(cards).filter((card) => {
                const title = card.querySelector('strong');
                if (!title) return false;
                return parseFloat(getComputedStyle(title).fontSize) * scale < 9;
            }).length;
            const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
            return {
                dom_nodes: document.getElementsByTagName('*').length,
                canvas_nodes: cards.length,
                zoom: zoom === null ? null : Math.round(zoom * 1000) / 1000,
                cards_below_9px: tiny,
                smallest_text_px: Number.isFinite(smallest) ? Math.round(smallest * 10) / 10 : null,
                horizontal_overflow: overflow,
                fcp_ms: fcp ? Math.round(fcp.startTime) : null,
                dom_ready_ms: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
                heap_mb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null,
            };
        }"""
    )


async def stress_trace(page, nodes: int, token: str, template: dict) -> dict:
    """Serve a scaled copy of a real trace; only the count is synthetic, every field shape is real."""
    sample = template["nodes"][0]
    edge_sample = (template.get("edges") or [{"id": "e", "source": "a", "target": "b", "type": "DEPENDS_ON"}])[0]
    payload = {
        **{key: value for key, value in template.items() if key not in {"nodes", "edges"}},
        "project_id": PROJECT,
        "nodes": [
            {
                **sample,
                "id": f"stress:{index}",
                "label": f"step {index}",
                "task_id": "task_stress",
                "status": ["COMPLETED", "COMPLETED", "FAILED"][index % 3],
                "parent_id": None,
            }
            for index in range(nodes)
        ],
        "edges": [
            {**edge_sample, "id": f"stress:e{index}", "source": f"stress:{index}", "target": f"stress:{index + 1}"}
            for index in range(nodes - 1)
        ],
        "truncated": False,
    }

    async def handler(route):
        await route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    await page.route("**/api/projects/*/execution-trace**", handler)
    started = time.monotonic()
    await page.goto(canvas_url("execution"), wait_until="domcontentloaded")
    try:
        await page.wait_for_function(
            f"() => document.querySelectorAll('.react-flow__node').length >= {nodes}",
            timeout=60000,
        )
    except Exception as error:  # noqa: BLE001 - record, do not fail the whole run
        return {"nodes": nodes, "error": f"{type(error).__name__}: mount did not reach {nodes} nodes"}
    mount_ms = round((time.monotonic() - started) * 1000)
    await page.wait_for_timeout(1200)
    metrics = await measure(page)

    # pan latency: drag the pane and time how long the browser needs to settle a frame
    latency = await page.evaluate(
        """async () => {
            const pane = document.querySelector('.react-flow__pane');
            if (!pane) return null;
            const box = pane.getBoundingClientRect();
            const started = performance.now();
            pane.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: box.x + 40, clientY: box.y + 40, pointerId: 1}));
            for (let step = 0; step < 20; step += 1) {
                pane.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: box.x + 40 + step * 8, clientY: box.y + 40 + step * 4, pointerId: 1}));
            }
            pane.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, clientX: box.x + 200, clientY: box.y + 120, pointerId: 1}));
            await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            return Math.round((performance.now() - started) * 10) / 10;
        }"""
    )
    await page.unroute("**/api/projects/*/execution-trace**")
    await page.screenshot(path=str(SHOTS / f"r21-stress-{nodes}.png"))
    return {"nodes": nodes, "mount_ms": mount_ms, "pan_ms": latency, **metrics}


async def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "before"
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1560, "height": 1000})
        page = await context.new_page()
        page.on("console", lambda message: results["console"].append(message.text) if message.type == "error" else None)
        token = await login(page)

        for mode in ("pipeline", "execution", "editor"):
            entry: dict[str, object] = {}
            for name, width in VIEWPORTS.items():
                await page.set_viewport_size({"width": width, "height": 1000 if width > 900 else 844})
                await page.goto(canvas_url(mode), wait_until="domcontentloaded")
                await page.wait_for_selector(".react-flow__node", timeout=45000)
                await page.wait_for_timeout(1500)
                entry[name] = await measure(page)
                await page.screenshot(path=str(SHOTS / f"r21-{phase}-{mode}-{name}.png"), full_page=False)
            results["real"][mode] = entry

        # the surfaces outside the canvas that Round 21 also touches
        for name, path in (("dashboard", "/"), ("runs", f"/runs?projectId={PROJECT}"), ("failures", f"/failures?projectId={PROJECT}")):
            await page.set_viewport_size({"width": 1560, "height": 1000})
            await page.goto(f"{WEB}{path}", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            results["real"][name] = {**(await measure(page)), "url": page.url}
            await page.screenshot(path=str(SHOTS / f"r21-{phase}-{name}-w1560.png"))

        real_trace = await page.evaluate(
            """async (project) => {
                const token = localStorage.getItem('ai-qa.auth-token');
                const response = await fetch(`/api/projects/${project}/execution-trace`, {headers: {Authorization: `Bearer ${token}`}});
                return response.ok ? response.json() : null;
            }""",
            PROJECT,
        )
        results["real"]["trace_template_nodes"] = len((real_trace or {}).get("nodes") or [])
        await page.set_viewport_size({"width": 1560, "height": 1000})
        if real_trace and real_trace.get("nodes"):
            for nodes in (100, 500, 1000):
                results["stress"][nodes] = await stress_trace(page, nodes, token, real_trace)

        await context.close()
        await browser.close()

    results["phase"] = phase
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    results["console"] = results["console"][:20]
    path = OUT / f"r21-perf-{phase}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in results.items() if key != "real"}, ensure_ascii=False)[:1200])
    for mode, entry in results["real"].items():
        if not isinstance(entry, dict):
            print(mode, entry)
            continue
        if not isinstance(entry.get("w1560"), dict):
            print(mode, {key: entry.get(key) for key in ("canvas_nodes", "smallest_text_px", "horizontal_overflow", "fcp_ms")})
            continue
        print(mode, {name: {"nodes": data["canvas_nodes"], "zoom": data["zoom"], "smallest_text": data["smallest_text_px"], "tiny": data["cards_below_9px"], "overflow": data["horizontal_overflow"]} for name, data in entry.items()})


if __name__ == "__main__":
    asyncio.run(main())
