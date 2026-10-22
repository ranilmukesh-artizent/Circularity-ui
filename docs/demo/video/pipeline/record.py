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


async def main():
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    out = D / 'rec'; out.mkdir(exist_ok=True)
    for f in out.glob('*.webm'): f.unlink()
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True, args=['--disable-ipc-flooding-protection', '--hide-scrollbars'])
        ctx = await br.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=str(out), record_video_size={'width': 1440, 'height': 900},
                                   color_scheme='light', reduced_motion='no-preference', locale='en-GB', timezone_id='UTC')
        await ctx.add_init_script(CURSOR_JS)
        page = await ctx.new_page()
        R = Rec(page)
        page.on('pageerror', lambda e: print('PAGE ERROR', e, flush=True))

        # 0 · title
        await page.goto(CARD('title')); await asyncio.sleep(0.8)
        await R.until(R.say('c0'), 0.8)

        # 1 · executive: the outcome first
        a0 = R.now()
        await page.goto(APP); await page.evaluate('()=>{try{localStorage.clear();sessionStorage.removeItem("__curpos")}catch(e){}}'); await page.reload()
        R.cuts.append([round(a0, 2), round(R.now(), 2)])
        await R.switch('exec', 'Executive', out=False)
        e = R.say('c1a')
        await R.point('#view .afbrief, #view .panel', 0)
        await asyncio.sleep(3.5)
        await R.point('text=Key figures')
        await R.until(e, 0.2)
        e = R.say('c1b')
        await R.click('#view button:has-text("Brief me")', after=0.3)
        await R.until(e, 1.6)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.6)

        # 2 · where the value leaks
        await page.goto(CARD('journey')); await asyncio.sleep(0.6)
        await R.until(R.say('c2'), 1.0)

        # 3 · planner: one asset, decided by agents
        a0 = R.now(); await page.goto(APP + '#/home'); await asyncio.sleep(1.2); R.cuts.append([round(a0, 2), round(R.now(), 2)])
        await R.switch('ops', 'Planner')
        e = R.say('c3a')
        await R.point('text=RT-1048 · submit for review')
        await R.until(e, 0.3)
        await R.open_case('RT-1048')
        e = R.say('c3b')
        await R.point('#view .afrec, #view .afc', 0); await asyncio.sleep(5.5)
        await R.point('text=ALTERNATIVES'); await asyncio.sleep(4.0)
        await R.point('text=NOT ELIGIBLE'); await asyncio.sleep(3.0)
        await R.point('#view .afgates', 0)
        await R.until(e, 0.3)
        await R.click('#view [data-act="afAssist"]', after=1.0)
        e = R.say('c3c')
        await R.type('#afq', 'What should we do with RT-1048, and why?', delay=35)
        await page.keyboard.press('Enter'); await asyncio.sleep(0.4)
        if await page.locator('#askp .aflines li').count() == 0:
            await R.click('#askp .afcomp button:has-text("Ask")', after=0.3)
        await R.until(e, 2.0)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.5)
        e = R.say('c3d')
        await R.point('text=AFTER APPROVAL'); await asyncio.sleep(3.0)
        await R.click('#view .afc [data-act="afDo"]:has-text("Submit for review")', after=0.5)
        await R.until(e, 1.0)

        # 4 · approver commits
        await R.switch('approver', 'Approver')
        e = R.say('c4p')
        await R.open_case('RT-1048')
        await R.until(e, 0.2)
        await R.click('#view .afc [data-act="afDo"]:has-text("Approve")', after=1.0)
        e = R.say('c4a')
        await R.point('#modal .mb p', 0); await asyncio.sleep(3.5)
        await R.point('#modal textarea, #ap-why', 0); await asyncio.sleep(2.5)
        await R.point('#modal :text("Raw instruction")')
        await R.until(e, 0.2)
        e = R.say('c4b')
        await R.click('#modal label:has-text("I reviewed evidence snapshot") input', after=0.6)
        await R.click('#modal [data-act="confirmApprove"]', after=1.2)
        await R.until(e, 1.4)

        # 5 · agents carry it through: the live run board
        await R.nav('orchestration')
        e = R.say('c5a')
        await asyncio.sleep(3.0)
        await R.point('#lrBoard .lrb.open .lrl', 0)
        await R.until(e, 0.4)
        e = R.say('c5a2')
        await R.point('#lrAgents'); await asyncio.sleep(1.5)
        await R.point('#lrTools'); await asyncio.sleep(1.5)
        await R.point('#lrAud')
        await R.click('#lrBoard [data-act="lrSpeed"][data-arg="2"]', after=0.5)
        await R.until(e, 1.0)
        await R.click('#lrBoard [data-act="lrSkip"]', after=0.6)
        await R.click('#lrBoard .lrb[data-n="5"] .lrh', after=0.4)
        e = R.say('c5b')
        await R.scroll_to('#lrBody-5', 'center')
        await R.point('#lrBody-5 .lrmd', 0); await asyncio.sleep(3.0)
        await R.point('#lrBody-5 .lrmods')
        await R.until(e, 0.3)
        await R.scroll_to('#lrBoard', 'start')
        await R.click('#lrBoard .lrb[data-n="6"] .lrh', after=0.4)
        e = R.say('c5c')
        await R.scroll_to('#lrBody-6', 'start')
        await R.point('#lrBody-6 .lrl', 5); await asyncio.sleep(2.5)
        await R.point('#lrBody-6 .lrmods'); await asyncio.sleep(2.0)
        await R.point('#lrBody-6 .lrmc .num', 1)
        await R.until(e, 0.3)
        await R.scroll_to('#lrBoard', 'start')
        await R.click('#lrBoard .lrb[data-n="8"] .lrh', after=0.4)
        e = R.say('c5d')
        for i in range(3):
            btn = '#lrBoard .lrb.open [data-act="afRunNext"]'
            await page.wait_for_selector(btn, timeout=20000)
            await R.click(btn, after=0.4)
            await R.lr_settled()
        await R.until(e, 0.8)
        await R.switch('finance', 'Finance')
        await R.nav('orchestration')
        await asyncio.sleep(1.5)
        await R.click('#lrBoard [data-act="lrSkip"]', after=0.6)
        e = R.say('c5e')
        await R.click('#lrBoard .lrb.open [data-act="afRunNext"]', after=0.4)
        await R.lr_settled()
        await R.until(e, 0.2)
        await R.scroll_to('#lrBody-10', 'center')
        e = R.say('c5f')
        await R.point('#lrBody-10 .lrres')
        await R.until(e, 1.2)

        # 6 · fits the landscape you already run
        await page.evaluate('()=>window.scrollTo({top:0,behavior:"smooth"})'); await asyncio.sleep(0.6)
        await R.switch('admin', 'Admin · IT')
        await R.nav('integration')
        await R.click('[data-act="intTab"][data-arg="map"]', after=0.8)
        e = R.say('c6a')
        await R.point('#view .phead p'); await asyncio.sleep(4.0)
        await R.point('text=Integration health')
        await R.until(e, 0.3)
        await R.nav('mcp')
        await R.click('#view .tabs [data-arg="mcp/client"]', after=0.6)
        e = R.say('c6b')
        await asyncio.sleep(4.0)
        await R.click('#view .tabs [data-arg="mcp/agents"]', after=0.6)
        await R.point('#mcpAgents .panel', 1)
        await R.until(e, 0.6)
        await R.nav('access')
        await R.click('#view .tabs [data-arg="access/autonomy"]', after=0.6)
        e = R.say('c6c')
        await R.point('#axAuto select', 0); await asyncio.sleep(4.0)
        await R.click('#view .tabs [data-arg="access/agentsx"]', after=0.6)
        await R.point('#axAgents input[type=checkbox]', 0)
        await R.until(e, 0.6)

        # 7 · it learns, and it proves it
        await R.switch('finance', 'Finance')
        await R.nav('analytics')
        e = R.say('c7')
        await R.point('text=additional net recovery vs baseline'); await asyncio.sleep(3.5)
        await R.point('text=confirmed avoided spend'); await asyncio.sleep(2.5)
        await R.point('text=median days to realize')
        await R.until(e, 0.4)
        e = R.say('c7b')
        await page.evaluate('()=>{const h=[...document.querySelectorAll("#view h2,#view h3")].find(x=>/Predicted vs actual/.test(x.textContent));h&&h.scrollIntoView({behavior:"smooth",block:"start"})}')
        await R.until(e, 1.0)

        # 8 · close
        await page.goto(CARD('close')); await asyncio.sleep(0.6)
        await R.until(R.say('c8'), 2.0)

        total = R.now()
        (D / 'timeline.json').write_text(json.dumps({'clips': R.tl, 'cuts': R.cuts, 'total': round(total, 2)}, indent=1))
        await page.close(); await ctx.close(); await br.close()
        print('recorded', round(total, 1), 's')

asyncio.run(main())
