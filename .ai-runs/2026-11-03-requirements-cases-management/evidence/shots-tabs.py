import json, urllib.request
from playwright.sync_api import sync_playwright
ISO='http://127.0.0.1:8010'; WEB='http://127.0.0.1:5173'; OUT='/tmp/aiqa-isolated/shots'
def api(m,p,b=None,t=None):
    r=urllib.request.Request(ISO+p,method=m,data=json.dumps(b).encode() if b is not None else None,
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+t} if t else {})})
    with urllib.request.urlopen(r) as x:
        raw=x.read(); return json.loads(raw) if raw else None
tok=api('POST','/api/auth/login',{'email':'admin@ai-qa.local','password':'adminpassword'})['access_token']
pid=api('GET','/api/projects',t=tok)[-1]['id']
reqs=api('GET',f'/api/requirements?project_id={pid}',t=tok)
rid=[r['id'] for r in reqs if '结算页优惠券' in r['title']][0]
report={}
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for w,h in ((1280,800),(1440,900),(1920,1080)):
        pg=b.new_page(viewport={'width':w,'height':h})
        pg.route(lambda u: u.startswith(WEB+'/api/'), lambda r: r.fulfill(response=r.fetch(url=r.request.url.replace(WEB,ISO))))
        pg.goto(WEB, wait_until='networkidle')
        if pg.locator('#login-email').count():
            pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
            pg.click('button[type=submit]'); pg.wait_for_timeout(3000)
        for tab,extra in (('requirements',''),('cases',''),('traceability',f'&trace={rid}')):
            pg.goto(f'{WEB}/projects/{pid}/management?tab={tab}{extra}', wait_until='networkidle')
            pg.wait_for_selector('.project-management-page'); pg.wait_for_timeout(800)
            pg.screenshot(path=f'{OUT}/closure-{tab}-{w}.png')
            metrics=pg.evaluate("""() => {
              const wrap=document.querySelector('.project-management-table-wrap');
              const t=document.querySelector('.project-management-table');
              return {pageOverflow: document.documentElement.scrollWidth-document.documentElement.clientWidth,
                      tableOverflow: wrap? t.scrollWidth-wrap.clientWidth : null,
                      rowHeight: t? Math.round(t.querySelector('tbody tr').getBoundingClientRect().height) : null};
            }""")
            report[f'{tab}-{w}']=metrics
        pg.close()
    b.close()
print(json.dumps(report, indent=1))
