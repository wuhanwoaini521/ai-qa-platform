import json, time
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:5173'; P=f'{BASE}/projects/proj_golden_shop_v1/management'
R={}
def up(pg,k): return pg.evaluate("(k) => new URL(location.href).searchParams.get(k)", k)
def wp(pg,k,v,t=20):
    end=time.time()+t
    while time.time()<end:
        if up(pg,k)==v: pg.wait_for_timeout(700); return
        pg.wait_for_timeout(100)
    raise AssertionError(f'{k}!={v} {pg.evaluate("location.href")}')
def settle(pg,t):
    pg.wait_for_function("(t) => document.activeElement && document.activeElement.id === 'management-tab-' + t", arg=t, timeout=10000); pg.wait_for_timeout(400)

with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900}); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type=='error' else None)
    pg.goto(BASE, wait_until='networkidle')
    if pg.locator('#login-email').count():
        pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
        pg.click('button[type=submit]'); pg.wait_for_selector('.page-container', timeout=15000)
    pg.goto(P, wait_until='networkidle'); pg.wait_for_selector('table.data-table')
    R['summary_default']=pg.locator('.project-management-filter-summary').inner_text()

    # keyboard: right x2, left x2, wrap
    pg.focus('#management-tab-requirements')
    pg.keyboard.press('ArrowRight'); wp(pg,'tab','cases'); settle(pg,'cases'); R['k_right1']=True
    pg.keyboard.press('ArrowRight'); wp(pg,'tab','traceability'); settle(pg,'traceability'); R['k_right2']=True
    pg.keyboard.press('ArrowRight'); wp(pg,'tab','requirements'); settle(pg,'requirements'); R['k_wrap']=True
    pg.keyboard.press('ArrowLeft'); wp(pg,'tab','traceability'); settle(pg,'traceability'); R['k_left1']=True
    pg.keyboard.press('ArrowLeft'); wp(pg,'tab','cases'); settle(pg,'cases'); R['k_left2']=True
    pg.keyboard.press('ArrowLeft'); wp(pg,'tab','requirements'); settle(pg,'requirements'); R['k_left3']=True

    # chips for each filter family
    pg.select_option('.project-management-filter select >> nth=1','unlinked'); wp(pg,'gap','unlinked')
    R['chip_gap']=[c.inner_text() for c in pg.locator('.management-filter-chip').all()]
    R['summary_after_gap']=pg.locator('.project-management-filter-summary > span').inner_text()
    R['rows_after_gap']=pg.locator('table.data-table tbody tr').count()
    pg.locator('.management-filter-chip').first.click(); wp(pg,'gap',None)
    R['chips_after_remove']=[c.inner_text() for c in pg.locator('.management-filter-chip').all()]
    pg.fill('.project-management-search input','购物车'); wp(pg,'q','购物车')
    R['chips_search']=[c.inner_text() for c in pg.locator('.management-filter-chip').all()]
    pg.wait_for_function("() => document.querySelectorAll('table.data-table tbody tr').length > 0")
    R['rows_search']=pg.locator('table.data-table tbody tr').count()
    pg.screenshot(path='/tmp/mgmt-evidence/v2-chips-search-1440.png')
    pg.click('.project-management-filter-summary button:has-text("清除筛选")'); wp(pg,'q',None)
    R['chips_cleared']=pg.locator('.management-filter-chip').count()

    # drawer open/close by click, backdrop, Escape; focus
    pg.locator('button:has-text("详情")').first.click(); pg.wait_for_selector('.management-detail-drawer')
    R['drawer_focus']=pg.evaluate("()=>document.activeElement.className")
    R['facts_rows']=pg.locator('.management-detail-facts > div').count()
    pg.click('.management-detail-backdrop', position={'x':10,'y':10}); pg.wait_for_selector('.management-detail-drawer', state='detached')
    R['closed_by_backdrop']=up(pg,'detail') is None
    pg.locator('button:has-text("详情")').nth(1).click(); pg.wait_for_selector('.management-detail-drawer')
    pg.keyboard.press('Escape'); pg.wait_for_selector('.management-detail-drawer', state='detached')
    R['closed_by_escape']=up(pg,'detail') is None
    # direct link
    pg.goto(P+'?detail=req_9c72a1dabe30', wait_until='networkidle'); pg.wait_for_selector('.management-detail-drawer')
    R['deep_link_title']=pg.locator('#management-detail-title').inner_text()

    R['errors']=[e for e in errs if 'DevTools' not in e and 'vite' not in e]
    b.close()
print(json.dumps(R, ensure_ascii=False, indent=2))
