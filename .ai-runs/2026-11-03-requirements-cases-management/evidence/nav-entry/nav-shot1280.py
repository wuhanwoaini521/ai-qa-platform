import json, urllib.request
from playwright.sync_api import sync_playwright
ISO='http://127.0.0.1:8010'; WEB='http://127.0.0.1:5173'
def api(m,p,b=None,t=None):
    r=urllib.request.Request(ISO+p,method=m,data=json.dumps(b).encode() if b is not None else None,
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+t} if t else {})})
    with urllib.request.urlopen(r) as x:
        raw=x.read(); return json.loads(raw) if raw else None
tok=api('POST','/api/auth/login',{'email':'admin@ai-qa.local','password':'adminpassword'})['access_token']
pid=[p['id'] for p in api('GET','/api/projects',t=tok) if p['name']=='导航验证 A'][0]
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for w,h in ((1280,800),(1920,1080)):
        pg=b.new_page(viewport={'width':w,'height':h})
        pg.route(lambda u: u.startswith(WEB+'/api/'), lambda r: r.fulfill(response=r.fetch(url=r.request.url.replace(WEB,ISO))))
        pg.goto(WEB, wait_until='networkidle')
        if pg.locator('#login-email').count():
            pg.fill('#login-email','admin@ai-qa.local'); pg.fill('#login-password','adminpassword')
            pg.click('button[type=submit]'); pg.wait_for_timeout(3000)
        pg.goto(f'{WEB}/projects/{pid}/management', wait_until='networkidle'); pg.wait_for_timeout(1200)
        m=pg.evaluate("""() => {
          const sb=document.querySelector('.app-sidebar'); const item=[...document.querySelectorAll('.nav-item')].find(n=>n.textContent.includes('需求与用例'));
          return {sidebarOverflow: sb.scrollWidth-sb.clientWidth, itemHeight: Math.round(item.getBoundingClientRect().height),
                  itemTop: Math.round(item.getBoundingClientRect().top), pageOverflow: document.documentElement.scrollWidth-document.documentElement.clientWidth};
        }""")
        print(w, json.dumps(m, ensure_ascii=False))
        pg.screenshot(path=f'/tmp/aiqa-isolated/nav-{w}.png')
        pg.close()
    b.close()
