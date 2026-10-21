"""Quick smoke probe of the Round 17 editor: create, add nodes, connect, save, publish."""
import asyncio
import json
import time

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173"
PROJECT = "proj_golden_shop_v1"
CANVAS = f"{BASE}/workspace/{PROJECT}?projectId={PROJECT}&stage=automation&view=canvas&canvas=editor"


async def login(page):
    await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    await page.fill("#login-email", "admin@ai-qa.local")
    await page.fill("#login-password", "adminpassword")
    await page.click("button[type=submit]")
    await page.wait_for_function("() => !!localStorage.getItem('ai-qa.auth-token')", timeout=30000)


async def main():
    out = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1560, "height": 1000})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await login(page)
        await page.goto(CANVAS, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        out["mode_tabs"] = await page.locator(".lw-canvas-mode").all_inner_texts()
        out["palette"] = (await page.locator(".wfe-palette-item").count()) if await page.locator(".wfe-palette").count() else 0
        out["empty_shown"] = await page.locator(".wfe-empty").count()

        # create a definition through the UI
        await page.fill('input[aria-label="新工作流名称"]', f"R17 探针工作流 {int(time.time())}")
        await page.click('button:has-text("新建工作流")')
        await page.wait_for_timeout(1800)
        out["message_after_create"] = await page.locator(".wfe-message").inner_text() if await page.locator(".wfe-message").count() else None

        for title in ("运行一次边界探索",):
            await page.click(f'.wfe-palette-item:has-text("{title}")')
            await page.wait_for_timeout(600)
        await page.click('.wfe-palette-item:has-text("请求人工审批")')
        await page.wait_for_timeout(400)
        await page.click('.wfe-palette-item:has-text("写入已批准的测试")')
        await page.wait_for_timeout(800)
        out["nodes_on_canvas"] = await page.locator(".wfe-node").count()

        # connect first node -> approval, approval -> write
        keys = await page.locator(".wfe-node").evaluate_all("els => els.map(e => e.getAttribute('data-node-key'))")
        out["keys"] = keys
        for source, target in ((keys[0], keys[1]), (keys[1], keys[2])):
            handle_source = page.locator(f'.wfe-node[data-node-key="{source}"] .react-flow__handle.source')
            handle_target = page.locator(f'.wfe-node[data-node-key="{target}"] .react-flow__handle.target')
            a = await handle_source.bounding_box()
            b = await handle_target.bounding_box()
            await page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
            await page.mouse.down()
            await page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=18)
            await page.mouse.up()
            await page.wait_for_timeout(500)
        out["edges_on_canvas"] = await page.locator(".react-flow__edge").count()

        # set the discovery input on the first node
        await page.click(f'.wfe-node[data-node-key="{keys[0]}"]')
        await page.wait_for_timeout(400)
        await page.fill('.wfe-inspector label:has-text("discovery_run_id") input', "qd_probe_value")
        await page.wait_for_timeout(300)

        await page.click('button:has-text("保存草稿")')
        await page.wait_for_timeout(2000)
        out["message_after_save"] = await page.locator(".wfe-message").inner_text() if await page.locator(".wfe-message").count() else None
        out["issues"] = await page.locator(".wfe-issues li strong").all_inner_texts()

        out["toolbar"] = await page.evaluate(
            "() => [...document.querySelectorAll('.wfe-toolbar button')].map(b => [b.textContent, b.disabled])"
        )
        out["edges_state"] = await page.locator('.react-flow__edge').count()
        print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
        await page.click('button:has-text("发布版本")')
        await page.wait_for_timeout(2200)
        out["message_after_publish"] = await page.locator(".wfe-message").inner_text() if await page.locator(".wfe-message").count() else None
        out["versions"] = await page.locator(".wfe-versions li").all_inner_texts()
        out["publish_disabled"] = await page.locator('button:has-text("发布版本")').is_disabled()

        await page.screenshot(path=".ai-runs/overnight-delivery/screenshots/r17-editor-smoke.png", full_page=False)
        out["console_errors"] = errors
        await browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


asyncio.run(main())
