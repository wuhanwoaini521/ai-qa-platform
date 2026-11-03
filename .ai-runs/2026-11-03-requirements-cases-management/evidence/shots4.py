from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:5173'; P=f'{BASE}/projects/proj_golden_shop_v1/management'
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1280,'height':800})
    pg.goto(BASE, wait_until='networkidle')
    if pg.locator('#login-email').count():
        pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
        pg.click('button[type=submit]'); pg.wait_for_selector('.page-container', timeout=15000)
    pg.goto(P+'?q=zzzz-nothing', wait_until='networkidle'); pg.wait_for_selector('.project-management-state')
    pg.screenshot(path='/tmp/mgmt-evidence/v3-nomatch-1440.png')
    print('clear buttons in state:', pg.locator('.project-management-state button').count(),
          'chips row clear:', pg.locator('.project-management-filter-summary button').count())
    pg.goto(P+'?tab=requirements&detail=req_9c72a1dabe30', wait_until='networkidle'); pg.wait_for_selector('.management-detail-drawer'); pg.wait_for_timeout(700)
    pg.screenshot(path='/tmp/mgmt-evidence/v3-drawer-1280.png')
    for w in (1440,1920):
        pg.set_viewport_size({'width':w,'height':900 if w==1440 else 1080}); pg.wait_for_timeout(500)
        pg.screenshot(path=f'/tmp/mgmt-evidence/v3-drawer-{w}.png')
    b.close()
