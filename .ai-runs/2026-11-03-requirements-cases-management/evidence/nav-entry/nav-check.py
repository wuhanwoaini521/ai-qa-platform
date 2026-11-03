import json, sys, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

ISO='http://127.0.0.1:8010'; WEB='http://127.0.0.1:5173'
def api(m, p, b=None, t=None):
    r=urllib.request.Request(ISO+p, method=m, data=json.dumps(b).encode() if b is not None else None,
        headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+t} if t else {})})
    try:
        with urllib.request.urlopen(r) as x:
            raw=x.read(); return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f'{m} {p} -> {e.code} {e.read().decode()[:400]}')
tok=api('POST','/api/auth/login',{'email':'admin@ai-qa.local','password':'adminpassword'})['access_token']
pa=api('POST','/api/projects',{'name':'导航验证 A','description':'','bootstrap_workspace':False},tok)
pb=api('POST','/api/projects',{'name':'导航验证 B','description':'','bootstrap_workspace':False},tok)
api('POST','/api/requirements',{'project_id':pa['id'],'title':'A 项目需求：购物车结算','description':'','acceptance_criteria':'','status':'DRAFT'},tok)
api('POST','/api/requirements',{'project_id':pb['id'],'title':'B 项目需求：地址簿维护','description':'','acceptance_criteria':'','status':'DRAFT'},tok)
r={'projects':{'a':pa['id'],'b':pb['id']}}
def label(pg, n):
    pg.wait_for_timeout(n)

with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    errors=[]
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.route(lambda u: u.startswith(WEB+'/api/'), lambda route: route.fulfill(response=route.fetch(url=route.request.url.replace(WEB, ISO))))
    pg.goto(WEB, wait_until='networkidle')
    if pg.locator('#login-email').count():
        pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
        pg.click('button[type=submit]'); pg.wait_for_timeout(3000)

    def nav_labels():
        return [pg.locator('.nav-item').nth(i).inner_text().strip() for i in range(pg.locator('.nav-item').count())]
    def active_nav():
        return pg.locator('.nav-item.active').inner_text().strip() if pg.locator('.nav-item.active').count() else None

    # 1. no project scope yet (projects list, all projects)
    pg.goto(f'{WEB}/projects', wait_until='networkidle'); pg.wait_for_timeout(800)
    r['nav_on_projects_list']=nav_labels()
    r['nav_has_requirements_without_scope']='需求与用例' in r['nav_on_projects_list']

    # 2. enter through the normal project entry (project overview -> management button)
    pg.goto(f'{WEB}/projects/{pa["id"]}', wait_until='networkidle')
    pg.wait_for_selector('.lc-tabs a.btn-primary'); pg.wait_for_timeout(500)
    pg.click('.lc-tabs a.btn-primary'); pg.wait_for_url('**/management'); pg.wait_for_timeout(1200)
    r['url_after_entry']=pg.url
    r['nav_after_entry']=nav_labels()
    r['active_after_entry']=active_nav()
    pg.screenshot(path='/tmp/aiqa-isolated/nav-1-entry.png')

    # 3. project switch through the sidebar selector
    pg.select_option('.sidebar-project-select', pb['id']); pg.wait_for_timeout(1500)
    r['url_after_switch']=pg.url
    r['select_value_after_switch']=pg.input_value('.sidebar-project-select')
    body=pg.inner_text('.project-management-page')
    r['switch_shows_b_project_data']=('B 项目需求：地址簿维护' in body) and ('A 项目需求：购物车结算' not in body)
    r['active_after_switch']=active_nav()
    pg.screenshot(path='/tmp/aiqa-isolated/nav-2-switched.png')

    # 4. refresh keeps state
    pg.reload(wait_until='networkidle'); pg.wait_for_timeout(1000)
    r['after_reload_url']=pg.url
    r['after_reload_active']=active_nav()
    r['after_reload_data_b']='B 项目需求：地址簿维护' in pg.inner_text('.project-management-page')

    # 5. back navigates to the A project page
    pg.go_back(); pg.wait_for_timeout(1200)
    r['after_back_url']=pg.url

    # 6. direct URL
    pg.goto(f'{WEB}/projects/{pb["id"]}/management', wait_until='networkidle'); pg.wait_for_timeout(1000)
    r['direct_url_active']=active_nav()
    r['direct_url_ok']='B 项目需求：地址簿维护' in pg.inner_text('.project-management-page')

    # 7. sidebar item click re-enters from another route
    pg.goto(f'{WEB}/quality', wait_until='networkidle'); pg.wait_for_timeout(800)
    pg.click(f'.nav-item:has-text("需求与用例")'); pg.wait_for_timeout(1200)
    r['url_from_sidebar_link']=pg.url

    # 8. language toggle
    pg.click('.sidebar-lang-toggle'); pg.wait_for_timeout(1200)
    r['en_labels']=nav_labels(); r['en_active']=active_nav()
    pg.screenshot(path='/tmp/aiqa-isolated/nav-3-en.png')
    pg.click('.sidebar-lang-toggle'); pg.wait_for_timeout(1200)
    r['zh_labels']=nav_labels()
    r['page_errors']=errors
    b.close()
print(json.dumps(r, ensure_ascii=False, indent=1))
