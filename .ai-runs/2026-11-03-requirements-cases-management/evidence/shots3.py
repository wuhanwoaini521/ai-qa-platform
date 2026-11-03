from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:5173'; P=f'{BASE}/projects/proj_golden_shop_v1/management'
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1280,'height':800})
    pg.goto(BASE, wait_until='networkidle')
    if pg.locator('#login-email').count():
        pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
        pg.click('button[type=submit]'); pg.wait_for_selector('.page-container', timeout=15000)
    for w,h in [(1280,800),(1440,900),(1920,1080)]:
        pg.set_viewport_size({'width':w,'height':h})
        for tab in ['requirements','cases','traceability']:
            pg.goto(f'{P}?tab={tab}', wait_until='networkidle'); pg.wait_for_selector('table.data-table'); pg.wait_for_timeout(700)
            pg.screenshot(path=f'/tmp/mgmt-evidence/v2-{tab}-{w}.png')
            print(w,tab,'page-overflow',pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth"),
                  'table-overflow',pg.evaluate("() => { const e=document.querySelector('.project-management-table-wrap'); return e? e.scrollWidth-e.clientWidth : null; }"))
    b.close()
