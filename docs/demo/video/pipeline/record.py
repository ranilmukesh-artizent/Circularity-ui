"""Record the agentic demo from the live UI with Playwright (system Chrome), timed to the narration clips.
Writes rec/*.webm and timeline.json ([clip, start_seconds]). python record.py [--only SCENE]"""
import asyncio, json, os, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

D = Path(__file__).resolve().parent
APP = 'file:///C:/repos/astra-prism-DI/ayush-ui/Circularity-ui/index.html?presenter=0'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DUR = json.loads((D / 'durations.json').read_text())
CARD = lambda n: (D / f'card_{n}.html').as_uri()

CURSOR_JS = r"""
(()=>{const mk=()=>{if(document.getElementById('__cur'))return;const c=document.createElement('div');c.id='__cur';
 c.style.cssText='position:fixed;left:720px;top:450px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(20,20,20,.82);border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);z-index:2147483647;pointer-events:none;transition:left .65s cubic-bezier(.3,.7,.2,1),top .65s cubic-bezier(.3,.7,.2,1)';
 document.documentElement.appendChild(c);
 const p=JSON.parse(sessionStorage.getItem('__curpos')||'null');if(p){c.style.transition='none';c.style.left=p[0]+'px';c.style.top=p[1]+'px';c.offsetWidth;c.style.transition=''}};
 window.__cur=(x,y)=>{mk();const c=document.getElementById('__cur');c.style.left=x+'px';c.style.top=y+'px';try{sessionStorage.setItem('__curpos',JSON.stringify([x,y]))}catch(e){}};
 window.__ripple=()=>{const c=document.getElementById('__cur');if(!c)return;const r=document.createElement('div');
  r.style.cssText='position:fixed;left:'+c.style.left+';top:'+c.style.top+';width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid #FFDD00;z-index:2147483646;pointer-events:none;transition:all .5s ease-out;opacity:1';
  document.documentElement.appendChild(r);requestAnimationFrame(()=>{r.style.width=r.style.height='54px';r.style.margin='-27px 0 0 -27px';r.style.opacity='0'});setTimeout(()=>r.remove(),600)};
 if(document.readyState!=='loading')mk();else document.addEventListener('DOMContentLoaded',mk)})();
"""

class Rec:
    def __init__(s, page):
        s.page, s.t0, s.tl, s.cuts = page, time.monotonic(), [], []
    async def switch(s, user, role, out=True):
        a = s.now()
        if out: await s.sign_out()
        await s.sign_in(user)
        s.cuts.append([round(a, 2), round(s.now(), 2)])
        await s.page.evaluate('''r=>{const d=document.createElement('div');d.textContent=r;d.style.cssText='position:fixed;left:50%;top:74px;transform:translateX(-50%);background:#141414;color:#FFDD00;font:700 17px Inter,system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:10px 22px;border-radius:999px;z-index:2147483646;box-shadow:0 6px 18px rgba(0,0,0,.25);transition:opacity .5s';document.documentElement.appendChild(d);setTimeout(()=>d.style.opacity='0',2600);setTimeout(()=>d.remove(),3200)}''', role)
    def now(s):
        return time.monotonic() - s.t0
    async def cut(s, coro):
        a = s.now(); await coro; s.cuts.append([round(a, 2), round(s.now(), 2)])
    def say(s, k):
        t = s.now(); s.tl.append([k, round(t, 2)]); print(f'{t:7.1f}s  {k}', flush=True); return t + DUR[k]
    async def until(s, t, pad=0.5):
        d = t + pad - s.now()
        if d > 0: await asyncio.sleep(d)
    async def point(s, sel, nth=0, must=False):
        loc = s.page.locator(sel).nth(nth) if isinstance(sel, str) else sel
        try:
            await loc.scroll_into_view_if_needed(timeout=8000 if must else 3000)
            b = await loc.bounding_box()
        except Exception as e:
            if must: raise
            s.miss = getattr(s, 'miss', 0) + 1
            print(f'  WARN point {sel!r}: not found', flush=True)
            await s.page.screenshot(path=str(D / f'miss{s.miss}.png'))
            return loc
        await s.page.evaluate('([x,y])=>window.__cur&&window.__cur(x,y)', [b['x'] + b['width'] / 2, b['y'] + min(b['height'] / 2, 18)])
        await asyncio.sleep(0.75)
        return loc
    async def click(s, sel, nth=0, after=0.6):
        loc = await s.point(sel, nth, must=True)
        await s.page.evaluate('()=>window.__ripple&&window.__ripple()')
        await loc.click(timeout=8000)
        await asyncio.sleep(after)
    async def type(s, sel, text, delay=75):
        await s.click(sel, after=0.2)
        await s.page.locator(sel).first.type(text, delay=delay)
    async def scroll_to(s, sel, block='center'):
        await s.page.evaluate('([q,b])=>{const e=document.querySelector(q);e&&e.scrollIntoView({behavior:"smooth",block:b})}', [sel, block])
        await asyncio.sleep(1.0)
    async def sign_in(s, user):
        await s.page.wait_for_selector('#si-id', timeout=15000)
        await s.type('#si-id', user, delay=30)
        await s.type('#si-pw', 'password', delay=20)
        await s.click('#siForm button[type=submit], #siForm .btn.pri', after=1.6)
    async def sign_out(s):
        await s.click('summary.acchip', after=0.5)
        await s.click('[data-act="signOut"]', after=1.0)
    async def open_case(s, cid):
        await s.type('#gs', cid, delay=90)
        await asyncio.sleep(0.5)
        await s.click(f'#results [data-act="openCase"][data-arg="{cid}"]', after=1.4)
        await s.click('#drawer button:has-text("Evaluate treatments")', after=1.4)
    async def nav(s, group):
        await s.click(f'.ngh[data-nav="{group}"]', after=1.2)
    async def lr_settled(s, timeout=60000):
        await s.page.wait_for_function('()=>S.lr&&S.lr.t>=S.lr.total', timeout=timeout)
        await asyncio.sleep(0.6)


async def glide_to(R, text, ms=1800, off=110):
    y = await R.page.evaluate('''([t,o])=>{const h=[...document.querySelectorAll("#view h1,#view h2,#view h3,#view h4")].find(x=>x.textContent.trim().startsWith(t));return h?h.getBoundingClientRect().top+scrollY-o:null}''', [text, off])
    if y is None:
        print(f'  WARN heading {text!r} not found', flush=True); return
    await R.page.evaluate('''([y,ms])=>new Promise(r=>{const s0=scrollY,d=y-s0,t0=performance.now();const f=t=>{const p=Math.min(1,(t-t0)/ms),e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;scrollTo(0,s0+d*e);p<1?requestAnimationFrame(f):r()};requestAnimationFrame(f)})''', [y, ms])
    await asyncio.sleep(0.3)

async def glide_in(R, root, frac=1.0, ms=4000):
    await R.page.evaluate('''([q,f,ms])=>new Promise(r=>{const Q=document.querySelector(q);if(!Q)return r();const el=[Q,...Q.querySelectorAll("*")].find(x=>x.scrollHeight>x.clientHeight+60&&/auto|scroll/.test(getComputedStyle(x).overflowY));if(!el)return r();const s0=el.scrollTop,d=(el.scrollHeight-el.clientHeight)*f-s0,t0=performance.now();const g=t=>{const p=Math.min(1,(t-t0)/ms);el.scrollTop=s0+d*(p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2);p<1?requestAnimationFrame(g):r()};requestAnimationFrame(g)})''', [root, frac, ms])

async def to_top(page):
    await page.evaluate('()=>window.scrollTo({top:0,behavior:"smooth"})'); await asyncio.sleep(0.7)

async def lr_settled(R, timeout=60000):
    await R.page.wait_for_function('()=>S.lr&&S.lr.t>=S.lr.total', timeout=timeout)
    await asyncio.sleep(0.5)

async def main():
    out = D / 'rec'; out.mkdir(exist_ok=True)
    for f in out.glob('*.webm'): f.unlink()
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True, args=['--disable-ipc-flooding-protection', '--hide-scrollbars'])
        ctx = await br.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=str(out), record_video_size={'width': 1440, 'height': 900},
                                   color_scheme='light', reduced_motion='no-preference', locale='en-GB', timezone_id='UTC')
        await ctx.add_init_script(CURSOR_JS)
        page = await ctx.new_page(); R = Rec(page)
        page.on('pageerror', lambda e: print('PAGE ERROR', e, flush=True))

        # title
        await page.goto(CARD('title')); await asyncio.sleep(0.8)
        await R.until(R.say('c0'), 0.6)

        # executive outcome
        a0 = R.now()
        await page.goto(APP); await page.evaluate('()=>{try{localStorage.clear();sessionStorage.removeItem("__curpos")}catch(e){}}'); await page.reload()
        R.cuts.append([round(a0, 2), round(R.now(), 2)])
        await R.switch('exec', 'Executive', out=False)
        e = R.say('c1')
        await R.point('#view .afc', 0); await asyncio.sleep(5.0)
        await R.point('text=Key figures')
        await R.until(e, 0.3)

        # plug and play: Connection Fabric, an agent diagnosing a feed, Workflow Studio drafting with AI
        await R.switch('admin', 'Admin · IT')
        await R.nav('integration')
        await R.click('[data-act="intTab"][data-arg="map"]', after=0.6)
        e = R.say('c2a')
        await R.point('#view .phead p'); await asyncio.sleep(3.0)
        await R.point('text=/integration health/i'); await asyncio.sleep(2.0)
        await glide_to(R, 'Connection Fabric', 1600, -260)
        await R.until(e, 0.2)
        await R.click('#view [data-act="afAssist"][data-arg="source|mkt"]:has-text("Diagnose")', after=0.8)
        e = R.say('c2b')
        await R.type('#afq', 'Why is the Market pricing feed stale, and how do I fix it?', delay=26)
        await page.keyboard.press('Enter'); await asyncio.sleep(0.5)
        if await page.locator('#askp .afm.a').count() == 0:
            await R.click('#askp .afcomp button:has-text("Ask")', after=0.3)
        await R.until(e, 1.4)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.4)
        await to_top(page)
        await R.click('[data-act="intTab"][data-arg="studio"]', after=0.8)
        await R.click('#afAskBtn', after=0.6)
        e = R.say('c2c')
        await R.type('#afq', 'Draft a workflow that ingests inspection results from SafetyCulture into the condition model every 15 minutes', delay=16)
        await page.keyboard.press('Enter'); await asyncio.sleep(2.5)
        await R.point('#askp .afc', 0); await asyncio.sleep(1.5)
        await R.click('#askp [data-act="afDo"]:has-text("Accept all")', after=0.8)
        await R.until(e, 0.3)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.4)

        # step 1: Asset & Product Intelligence
        await R.switch('ops', 'Planner')
        await R.nav('product')
        await R.click('#view a[href="#/product/asset/RT-1048"]', after=1.4)
        e = R.say('c3a')
        await R.point('#view h1'); await asyncio.sleep(2.0)
        await glide_to(R, 'Retrieved from enterprise systems', 2200)
        await asyncio.sleep(2.5)
        await glide_to(R, 'Lease end, return and transit', 1500)
        await R.until(e, 0.2)
        e = R.say('c3b')
        await glide_to(R, 'Diagnostic condition', 1800); await asyncio.sleep(0.8)
        await glide_to(R, 'Inspection findings', 1500); await asyncio.sleep(0.8)
        await glide_to(R, 'Lifecycle evidence timeline', 1500)
        await R.until(e, 0.3)

        # steps 2-4: Treatment Intelligence, evidence snapshot, pathways, why, what-if
        await to_top(page)
        await R.click('#view details.asmenu > summary', after=0.6)
        await R.click('#view details.asmenu [data-act="go"][data-arg="product/RT-1048"]', after=1.4)
        e = R.say('c4a')
        await R.point('#view .afrec', 0); await asyncio.sleep(1.5)
        await R.click('#view [data-act="snapshot"]', after=1.0)
        await glide_in(R, '#drawer', 0.55, 4500)
        await R.until(e, 0.2)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.5)
        await page.evaluate('()=>{try{closeDrawer(true)}catch(e){}}'); await asyncio.sleep(0.4)
        await R.click('#view .afc [data-act="afDo"]:has-text("Full analysis")', after=0.8)
        e = R.say('c4b')
        await glide_to(R, 'All pathways', 2000)
        await R.point('#view table', 0)
        await R.until(e, 0.2)
        e = R.say('c4c')
        await glide_to(R, 'Why this outcome', 2000); await asyncio.sleep(2.5)
        await glide_to(R, 'Predicted outcomes and comparison', 1800)
        await R.until(e, 0.2)
        e = R.say('c4d')
        await glide_to(R, 'What-if and edge cases', 2000)
        await R.click('#view [data-act="tiPreset"][data-arg="demand"]', after=1.0)
        await R.point('#view .tiwi, #view #wiSim', 0)
        await R.until(e, 0.8)
        await R.click('#view [data-act="tiPreset"][data-arg="demand"]', after=0.5)

        # step 5: submit, then the approver commits
        e = R.say('c5a')
        await glide_to(R, 'Next best action', 1800)
        sub = '#jgmount [data-act]:has-text("Submit RT-1048 for review"):visible'
        if await page.locator(sub).count():
            await R.click(sub, after=0.8)
        else:
            print('  WARN bottom-bar submit missing; using the packet button', flush=True)
            await to_top(page); await R.click('#view .afc [data-act="afDo"]:has-text("Submit for review")', after=0.8)
        await R.until(e, 0.4)
        await R.switch('approver', 'Approver')
        await R.open_case('RT-1048')
        await R.click('#view .afc [data-act="afDo"]:has-text("Approve")', after=1.0)
        e = R.say('c5b')
        await R.point('#modal .mb p', 0); await asyncio.sleep(3.0)
        await R.point('#modal textarea', 0); await asyncio.sleep(2.0)
        await R.click('#modal label:has-text("I reviewed evidence snapshot") input', after=0.5)
        await R.click('#modal [data-act="confirmApprove"]', after=0.8)
        await R.until(e, 0.6)

        # steps 6-9: agents on the live run board
        await R.nav('orchestration')
        e = R.say('c6a')
        await asyncio.sleep(3.5)
        await R.point('#lrBoard .lrb.open .lrl', 0); await asyncio.sleep(2.5)
        await R.point('#lrAgents')
        await R.until(e, 0.2)
        await R.click('#lrBoard [data-act="lrSkip"]', after=0.5)
        await R.click('#lrBoard .lrb[data-n="6"] .lrh', after=0.3)
        e = R.say('c6b')
        await R.scroll_to('#lrBody-6 .lrmods', 'center')
        await R.point('#lrBody-6 .lrmc .num', 1); await asyncio.sleep(1.8)
        await R.scroll_to('#lrBoard', 'start')
        await R.click('#lrBoard .lrb[data-n="5"] .lrh', after=0.4)
        await R.point('#lrBody-5 .lrmd', 0)
        await R.until(e, 0.2)
        await R.click('#lrBoard .lrb[data-n="8"] .lrh', after=0.4)
        e = R.say('c6c')
        for i in range(3):
            btn = '#lrBoard .lrb.open [data-act="afRunNext"]'
            await page.wait_for_selector(btn, timeout=20000)
            await R.click(btn, after=0.3)
            await lr_settled(R)
        await R.until(e, 0.3)

        # Finance confirms the outcome off camera; back on the approver's board
        async def offcam():
            await R.sign_out(); await R.sign_in('finance'); await R.nav('orchestration'); await asyncio.sleep(1.0)
            await R.click('#lrBoard [data-act="lrSkip"]', after=0.4)
            await R.click('#lrBoard .lrb.open [data-act="afRunNext"]', after=0.4); await lr_settled(R)
            await R.sign_out(); await R.sign_in('approver'); await R.nav('orchestration'); await asyncio.sleep(0.8)
            await R.click('#lrBoard [data-act="lrSkip"]', after=0.4)
            await page.evaluate('()=>ACT.afRunSel(10)'); await asyncio.sleep(0.3)
            await R.scroll_to('#lrBody-10', 'center')
        await R.cut(offcam())

        # step 10: reconcile and learn
        e = R.say('c7')
        await R.point('#lrBody-10 .lrres'); await asyncio.sleep(3.0)
        await to_top(page)
        await R.click('#view a.btn:has-text("Open RT-1048")', after=1.4)
        await R.click('#view .afc [data-act="afDo"]:has-text("Full analysis")', after=0.6)
        await glide_to(R, 'Reconcile and learn', 2400)
        await R.until(e, 0.8)

        # close
        await page.goto(CARD('close')); await asyncio.sleep(0.6)
        await R.until(R.say('c8'), 1.8)

        total = R.now()
        (D / 'timeline.json').write_text(json.dumps({'clips': R.tl, 'cuts': R.cuts, 'total': round(total, 2)}, indent=1))
        await page.close(); await ctx.close(); await br.close()
        print('recorded', round(total, 1), 's', 'after cuts', round(total - sum(b - a for a, b in R.cuts), 1))

asyncio.run(main())
