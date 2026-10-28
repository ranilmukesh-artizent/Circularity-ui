"""Record the CXO demo (docs/PLAN_CXO_DEMO_VIDEO.md, docs/demo/VIDEO_SCRIPT_CXO.md) from the live UI with Playwright (system Chrome),
timed to the narration clips in narration_cxo.json. Writes rec_cxo/*.webm and timeline_cxo.json. python record_cxo.py
Order: DI landing → Recover sign-in (Planner) → Returned assets → RT-1048 and its photo → stages 1–5 → stage 6 Explain (why, evidence,
what-if) → submit → Approver approves → stages 8–9 → (Finance confirms, off camera) → stage 10 → Admin: Connection Fabric, an agent
drafting and changing a workflow → Analytics predicted vs actual with the agent → close card."""
import asyncio, json, time
from pathlib import Path
from playwright.async_api import async_playwright

D = Path(__file__).resolve().parent
ROOT = 'file:///C:/repos/astra-prism-DI/ayush-ui/Circularity-ui/'
APP = ROOT + 'index.html'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DUR = json.loads((D / 'durations_cxo.json').read_text())
CARD = (D / 'card_close_cxo.html').as_uri()
CASE = 'RT-1048'

CURSOR_JS = r"""
(()=>{const mk=()=>{if(document.getElementById('__cur'))return;const c=document.createElement('div');c.id='__cur';
 c.style.cssText='position:fixed;left:720px;top:450px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(20,20,20,.82);border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);z-index:2147483647;pointer-events:none;transition:left .65s cubic-bezier(.3,.7,.2,1),top .65s cubic-bezier(.3,.7,.2,1)';
 document.documentElement.appendChild(c);
 const p=JSON.parse(sessionStorage.getItem('__curpos')||'null');if(p){c.style.transition='none';c.style.left=p[0]+'px';c.style.top=p[1]+'px';c.offsetWidth;c.style.transition=''}};
 window.__cur=(x,y,fast)=>{mk();const c=document.getElementById('__cur');if(fast){c.style.transition='left .12s linear,top .12s linear'}else{c.style.transition=''}c.style.left=x+'px';c.style.top=y+'px';try{sessionStorage.setItem('__curpos',JSON.stringify([x,y]))}catch(e){}};
 window.__ripple=()=>{const c=document.getElementById('__cur');if(!c)return;const r=document.createElement('div');
  r.style.cssText='position:fixed;left:'+c.style.left+';top:'+c.style.top+';width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid #FFDD00;z-index:2147483646;pointer-events:none;transition:all .5s ease-out;opacity:1';
  document.documentElement.appendChild(r);requestAnimationFrame(()=>{r.style.width=r.style.height='54px';r.style.margin='-27px 0 0 -27px';r.style.opacity='0'});setTimeout(()=>r.remove(),600)};
 if(document.readyState!=='loading')mk();else document.addEventListener('DOMContentLoaded',mk)})();
"""
CAPTION_JS = '''r=>{const d=document.createElement('div');d.textContent=r;d.style.cssText='position:fixed;left:50%;top:74px;transform:translateX(-50%);background:#141414;color:#FFDD00;font:700 17px Inter,system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:10px 22px;border-radius:999px;z-index:2147483646;box-shadow:0 6px 18px rgba(0,0,0,.25);transition:opacity .5s';document.documentElement.appendChild(d);setTimeout(()=>d.style.opacity='0',2600);setTimeout(()=>d.remove(),3200)}'''


class Rec:
    def __init__(s, page):
        s.page, s.t0, s.tl, s.cuts, s.scrolls, s.scene = page, time.monotonic(), [], [], {}, ''
    def now(s):
        return time.monotonic() - s.t0
    def say(s, k):
        t = s.now(); s.tl.append([k, round(t, 2)]); s.scene = k; print(f'{t:7.1f}s  {k}', flush=True); return t + DUR[k]
    async def until(s, t, pad=0.5):
        d = t + pad - s.now()
        if d > 0: await asyncio.sleep(d)
        elif d < -0.3: print(f'  OVER {s.scene} by {-d:.1f}s', flush=True)
    async def cut(s, coro):
        a = s.now(); await coro; s.cuts.append([round(a, 2), round(s.now(), 2)])
    async def caption(s, text):
        await s.page.evaluate(CAPTION_JS, text)
    async def point(s, sel, nth=0, must=False, settle=0.75):
        loc = s.page.locator(sel).nth(nth) if isinstance(sel, str) else sel
        try:
            y0 = await s.page.evaluate('()=>scrollY')
            await loc.scroll_into_view_if_needed(timeout=8000 if must else 3000)
            if await s.page.evaluate('()=>scrollY') != y0: s.scrolls[s.scene] = s.scrolls.get(s.scene, 0) + 1
            b = await loc.bounding_box()
        except Exception:
            if must: raise
            print(f'  WARN point {sel!r}: not found', flush=True); return loc
        await s.page.evaluate('([x,y])=>window.__cur&&window.__cur(x,y)', [b['x'] + b['width'] / 2, b['y'] + min(b['height'] / 2, 18)])
        await asyncio.sleep(settle)
        return loc
    async def click(s, sel, nth=0, after=0.6):
        loc = await s.point(sel, nth, must=True)
        await s.page.evaluate('()=>window.__ripple&&window.__ripple()')
        await loc.click(timeout=8000)
        await asyncio.sleep(after)
    async def hover(s, sel, nth=0, after=0.6):
        loc = await s.point(sel, nth, settle=0.5)
        try: await loc.hover(timeout=3000)
        except Exception: pass
        await asyncio.sleep(after)
    async def type(s, sel, text, delay=60):
        await s.click(sel, after=0.2)
        await s.page.locator(sel).first.type(text, delay=delay)
    async def go(s, h, after=1.3):
        await s.page.evaluate('h=>{location.hash=h}', h); await asyncio.sleep(after); await s.page.evaluate('()=>scrollTo(0,0)')
    async def sign_in(s, user):
        await s.page.wait_for_selector('#si-id', timeout=15000)
        await s.type('#si-id', user, delay=45)
        await s.type('#si-pw', 'password', delay=25)
        await s.click('#siForm button[type=submit], #siForm .btn.pri', after=1.6)
    async def sign_out(s):
        await s.page.keyboard.press('Escape')
        await s.click('summary.acchip', after=0.4)
        await s.click('[data-act="signOut"]', after=0.9)
    async def switch(s, user, caption=None):
        a = s.now(); await s.sign_out(); await s.sign_in(user); s.cuts.append([round(a, 2), round(s.now(), 2)])
        if caption: await s.caption(caption)
    async def glide(s, sel=None, to='bottom', ms=2200):
        '''smooth-scroll the window (sel None, to = an element selector to bring near the top) or an element's own scroll box (to = 'bottom'|'top')'''
        await s.page.evaluate('''([q,to,ms])=>new Promise(r=>{const el=q?document.querySelector(q):null;const box=el||document.scrollingElement;let y1;
          if(!q){const t=document.querySelector(to);y1=t?t.getBoundingClientRect().top+scrollY-110:0}else{y1=to==='top'?0:box.scrollHeight-box.clientHeight}
          const y0=box.scrollTop,t0=performance.now();const f=t=>{const p=Math.min(1,(t-t0)/ms),e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;box.scrollTop=y0+(y1-y0)*e;p<1?requestAnimationFrame(f):r()};requestAnimationFrame(f)})''', [sel, to, ms])
        s.scrolls[s.scene] = s.scrolls.get(s.scene, 0) + 1
        await asyncio.sleep(0.3)
    async def ask(s, button, chip=None, wait=2.6):
        '''open the agent panel from a button on the page, optionally pick a suggestion, and let the answer show'''
        await s.click(button, after=1.0)
        if chip:
            try: await s.click(f'#askp button:has-text("{chip}") >> nth=-1', after=wait)
            except Exception: print('  WARN no chip', chip, flush=True)
        else: await asyncio.sleep(wait)
    async def unask(s):
        await s.page.keyboard.press('Escape'); await asyncio.sleep(0.4)
    async def drag_range(s, sel, frm, to, ms=1400):
        """drag a range input's thumb from value frm to value to (both 50–150) with the visible cursor"""
        b = await s.page.locator(sel).bounding_box()
        x = lambda v: b['x'] + 8 + (b['width'] - 16) * (v - 50) / 100
        y = b['y'] + b['height'] / 2
        await s.page.evaluate('([x,y])=>window.__cur(x,y)', [x(frm), y]); await asyncio.sleep(0.8)
        await s.page.mouse.move(x(frm), y); await s.page.mouse.down()
        steps = 24
        for i in range(1, steps + 1):
            v = frm + (to - frm) * i / steps
            await s.page.mouse.move(x(v), y); await s.page.evaluate('([x,y])=>window.__cur(x,y,1)', [x(v), y]); await asyncio.sleep(ms / 1000 / steps)
        await s.page.mouse.up()


async def main():
    out = D / 'rec_cxo'; out.mkdir(exist_ok=True)
    for f in out.glob('*.webm'): f.unlink()
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True, args=['--disable-ipc-flooding-protection', '--hide-scrollbars', '--allow-file-access-from-files'])
        ctx = await br.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=str(out), record_video_size={'width': 1440, 'height': 900},
                                   color_scheme='light', reduced_motion='no-preference', locale='en-GB', timezone_id='UTC')
        await ctx.add_init_script(CURSOR_JS)
        page = await ctx.new_page(); R = Rec(page)
        page.on('pageerror', lambda e: print('PAGE ERROR', e, flush=True))

        # reset the app to its seeded state, off camera
        a0 = R.now()
        await page.goto(APP); await page.evaluate('()=>{try{localStorage.clear();sessionStorage.removeItem("__curpos")}catch(e){}}')
        await page.goto(ROOT + 'framework/index.html'); await asyncio.sleep(1.2)
        R.cuts.append([round(a0, 2), round(R.now(), 2)])

        # 0 · the DI landing page: three applications
        e = R.say('x0')
        await R.point('h1', settle=1.5)
        await R.point('a.vcard.rec', settle=1.5)
        await R.point('text=Identify the most economically sound', settle=3.0)
        await R.point('text=Bring signals, alternatives', settle=9.0)
        await R.point('text=Validate commercial and operational', settle=8.0)
        await R.until(e, -2.4)
        await R.click('a.vcard.rec', after=1.4)

        # 1 · sign in as the Planner
        e = R.say('x1')
        await R.sign_in('ops')
        await R.until(e, 0.2)
        await R.point('#app >> text=Decision Workb >> nth=0', settle=0.4)
        await R.go('#/product/received', after=1.0)

        # 2 · what came back; RT-1048 and its photo
        e = R.say('x2a')
        await R.point('#view >> text=received this cycle >> nth=0', settle=2.0)
        await R.point('#view >> text="Start here"', settle=1.5)
        await R.until(e, 0.2)
        e = R.say('x2b')
        await R.click(f'#view a[href="#/product/asset/{CASE}"]', after=1.6)
        await R.click('#view img[src*="assets/products/"]', after=3.2)
        await page.keyboard.press('Escape'); await asyncio.sleep(0.5)
        await R.point('#view >> text=Overall asset health', settle=1.6)
        await R.point('#view >> text=Return authorisation', settle=1.2)
        await R.until(e, 0.1)
        e = R.say('x2c')
        await R.ask('#view button:has-text("Ask about RT-1048") >> nth=0', 'Summarise this asset', wait=3.0)
        await R.until(e, 0.3)
        await R.unask()

        # 3 · stages 1–5: what the agents did on arrival, one stage at a time
        await R.go(f'#/product/{CASE}/overview')
        e = R.say('x3o')
        await R.point('#view >> text=Arrive >> nth=0', settle=1.6)
        await R.until(e, 0.1)
        for n, k in ((1, 'x3s1'), (2, 'x3s2'), (3, 'x3s3'), (4, 'x3s4'), (5, 'x3b')):
            await R.go(f'#/product/{CASE}/stage/{n}', after=0.9)
            e = R.say(k)
            await R.point('#view h1', settle=0.9)
            await R.point('#view >> text=What happened >> nth=0', settle=1.4)
            if n == 5:
                await R.point('#view >> text=MRO >> nth=0', settle=1.2)
                await R.ask('#view [data-act="stAsk"]', wait=6.0)
                await R.until(e, 0.3); await R.unask(); continue
            await R.point('#view >> text=What it means >> nth=0', settle=0.6)
            await R.until(e, 0.15)

        # 4 · stage 6: the decision, why, evidence, what-if
        await R.go(f'#/product/{CASE}/stage/6')
        e = R.say('x4a')
        await R.point('#view h1', settle=1.5)
        await R.point('#view >> text=All six passed', settle=2.0)
        await R.point('#view >> text=Not eligible', settle=2.0)
        await R.until(e, 0.2)
        e = R.say('x4b')
        await R.point('#view >> text=Recommended: Redeploy', settle=2.0)
        await R.point('#view >> text=Model · Prediction model >> nth=0', settle=3.0)
        await R.point('#view >> text=Predicted net', settle=1.5)
        await R.until(e, 0.2)
        await R.click('#view [data-act="cxExplain"]', after=1.0)
        e = R.say('x4c')
        for i in range(3):
            await R.hover('#cxX .cxd', nth=i, after=1.7)
        await R.point('#cxX .cxr .cxph', settle=1.2)
        await R.hover('#cxX .cxev[data-k="cost"]', after=1.0)
        await R.until(e, 0.2)
        e = R.say('x4d')
        await R.drag_range('#cx-sc-cost', 100, 130)
        await R.point('#cxImpact .tiwis', settle=2.2)
        await R.click('#cxX [data-act="cxPreset"][data-arg="demand"]', after=0.6)
        await R.point('#cxImpact .tiwis', settle=1.2)
        await R.until(e, 0.6)
        e = R.say('x4e')
        await asyncio.sleep(1.6)
        await R.click('#cxX [data-act="cxClose"]', after=0.6)
        await page.evaluate("()=>{Object.assign(S.scen,{purchase:1,cost:1,service:1,market:1,demandOff:false});route(true)}"); await asyncio.sleep(0.4)
        await R.click('#view button:has-text("Submit RT-1048 for review")', after=1.0)
        await R.until(e, 0.4)

        # 5 · stage 7: a second person approves
        await R.switch('approver', 'Approver')
        await R.go(f'#/product/{CASE}/stage/7')
        e = R.say('x5')
        await R.click('#view button:has-text("Approve Redeploy")', after=1.2)
        await R.point('#modal textarea', settle=2.6)
        cb = page.locator('#modal input[type=checkbox]')
        for i in range(await cb.count()):
            await R.click(cb.nth(i), after=0.4)
        await R.click('#modal [data-act="confirmApprove"]', after=1.2)
        await R.until(e, 0.3)

        # 6 · stages 8–9: the agent sends the work out; each system reports back
        await R.go(f'#/product/{CASE}/stage/8')
        e = R.say('x6')
        await R.point('#view >> text=MRO >> nth=0', settle=1.2)
        for i in range(4):
            b = page.locator('#view button:has-text("Check for the next acknowledgement")')
            try: await b.first.wait_for(state='visible', timeout=10000)
            except Exception: print('  WARN no ack button', i, flush=True); break
            await R.click(b.first, after=1.0)
        await R.go(f'#/product/{CASE}/stage/9', after=0.9)
        await R.click('#view [data-act="cxRunNext"]', after=1.2)
        await R.until(e, 0.2)

        # Finance confirms the outcome off camera; the Admin carries on from stage 10
        async def offcam():
            await R.sign_out(); await R.sign_in('finance'); await R.go(f'#/product/{CASE}/stage/9')
            await page.locator('#view button:has-text("Confirm the outcome")').first.click(); await asyncio.sleep(1.2)
            if await page.locator('#modal:visible').count():
                m = page.locator('#modal button.pri')
                if await m.count(): await m.first.click(); await asyncio.sleep(1.0)
            await R.sign_out(); await R.sign_in('admin'); await R.go(f'#/product/{CASE}/stage/10')
        await R.cut(offcam())

        # 7 · stage 10: reconcile and learn
        e = R.say('x7')
        await R.point('#view >> text=Predicted $9,600', settle=2.0)
        await R.point('#view >> text=Actual >> nth=0', settle=2.5)
        await R.ask('#view [data-act="stAsk"]', wait=1.0)
        await R.point('#askp >> text=Why it matters >> nth=-1', settle=4.0)
        await R.until(e, 0.3)
        await R.unask()

        # 7b · the agents' run, replayed at 2x on the run board
        await R.go('#/orchestration/run', after=1.2)
        await R.click('[data-act="lrReplay"] >> nth=0', after=0.3)
        await R.click('[data-act="lrSpeed"][data-arg="2"]', after=0.2)
        await R.caption('Replay · 2× speed')
        e = R.say('x7r')
        await R.point('#view >> text=agents >> nth=0', settle=2.0)
        await R.point('#view >> text=tool calls >> nth=0', settle=2.0)
        for i in range(4):
            await R.point('#lrBoard .lrb.open, #lrBoard', settle=3.0)
        await R.until(e, -1.2)
        if not await page.evaluate('()=>S.lr&&S.lr.t>=S.lr.total'):
            await R.click('#lrBoard [data-act="lrSkip"], [data-act="lrSkip"] >> nth=0', after=0.8)
        await R.until(e, 0.3)

        # 8 · Connection Fabric, as the Admin
        await R.go('#/integration/overview', after=1.0)
        await R.caption('Admin · IT')
        e = R.say('x8a')
        await R.point('#view button:has-text("ERP")', settle=1.6)
        await R.point('#view button:has-text("OMS")', settle=1.4)
        await R.point('#view button:has-text("MRO")', settle=1.6)
        await R.point('#view button:has-text("WMS")', settle=1.4)
        await R.point('#view >> text=Connected >> nth=0', settle=2.0)
        await R.until(e, 0.2)
        # the source map: the whole graph, systems picked to light their data paths, a stale feed diagnosed by the agent
        await R.point('#view >> text="Source Map" >> nth=0', settle=0.4); await R.go('#/integration/map', after=0.8)
        e = R.say('x8b')
        await R.glide(None, '#frGv', ms=1600)
        await R.click('#view [data-act="cxMapWide"]', after=1.0)
        for i in range(4): await R.click('#view [data-act="frSmZ"][data-arg="-1"]', after=0.25)
        await R.click('#frGv [data-arg="repair"]', after=4.6)
        await R.click('#frGv [data-arg="erp"]', after=3.6)
        await R.until(e, 0.1)
        e = R.say('x8b2')
        await R.glide('#frGv', 'bottom', ms=2600)
        await R.point('#frGv >> text=Decision >> nth=-1', settle=1.4)
        await R.glide('#frGv', 'top', ms=1600)
        await R.click('#frGv [data-arg="mkt"]', after=1.0)
        await R.ask('#view button:has-text("Diagnose") >> nth=0', 'Diagnose Market pricing', wait=3.0)
        await R.until(e, 0.3)
        await R.unask()
        await R.point('#view >> text="Source Tables" >> nth=0', settle=0.4); await R.go('#/integration/tables', after=0.8)
        e = R.say('x8c')
        await R.point('#view >> text=Links between tables >> nth=0', settle=1.2)
        await R.ask('#view button:has-text("Suggest links")', 'Suggest links between these tables', wait=3.0)
        await R.until(e, 0.2)
        await R.unask()
        await R.point('#view >> text="Canonical Models" >> nth=0', settle=0.4); await R.go('#/integration/models', after=0.8)
        e = R.say('x8d')
        await R.point('#view >> text=Asset & component >> nth=0', settle=2.8)
        await R.point('#view >> text=Condition & eligibility >> nth=0', settle=2.8)
        await R.point('#view >> text=Fed by >> nth=1', settle=2.0)
        await R.until(e, 0.2)
        await R.point('#view >> text="Workflow Studio" >> nth=0', settle=0.4); await R.go('#/integration/studio', after=0.8)
        e = R.say('x8e')
        await R.point('#view >> text=Total workflows >> nth=0', settle=2.6)
        await R.point('#view >> text=Published >> nth=0', settle=2.2)
        await R.until(e, 0.1)
        e = R.say('x8f')
        await R.click('#afAskBtn', after=0.4)
        await R.type('#afq', 'Draft a workflow that brings repair and bench-test results in from the MRO workshop every 15 minutes', delay=6)
        await page.keyboard.press('Enter'); await asyncio.sleep(2.0)
        await R.click('#askp [data-act="afDo"]:has-text("Accept")', after=3.6)
        await R.until(e, 0.3)
        e = R.say('x8g')
        await R.click('#afAskBtn', after=0.4)
        await R.type('#afq', 'Run it every five minutes, and flag any unit that fails its bench test', delay=12)
        await page.keyboard.press('Enter'); await asyncio.sleep(2.0)
        await R.point('#askp .afplan', settle=1.4)
        await R.click('#askp [data-act="afDo"]:has-text("Apply to the canvas")', after=1.2)
        await R.point('#view .wfn.cxnew', settle=1.0)
        await R.until(e, 0.5)

        # 9 · Analytics: predicted against actual, with the agent beside it
        await page.keyboard.press('Escape')
        await R.go('#/analytics/predicted', after=1.2)
        e = R.say('x9a')
        await R.point('#view .cxfocus svg >> nth=0', settle=3.0)
        await R.point('#view >> text=v1.3 >> nth=0', settle=1.0)
        await R.until(e, 0.2)
        e = R.say('x9b')
        await R.point('#view >> text=17.7% >> nth=0', settle=1.2)
        await R.point('#view >> text=12.5% >> nth=0', settle=1.2)
        await R.click('#view .cxfocus [data-act="afAssist"] >> nth=0', after=1.0)
        await R.click('#askp button:has-text("What changed and why")', after=2.0)
        await R.until(e, 0.6)

        # 10 · close
        await page.goto(CARD); await page.evaluate("()=>{const c=document.getElementById('__cur');c&&c.remove();window.__cur=()=>{}}"); await asyncio.sleep(0.6)
        e = R.say('x10a'); await R.until(e, 0.4)
        e = R.say('x10b'); await R.until(e, 1.4)

        total = R.now()
        (D / 'timeline_cxo.json').write_text(json.dumps({'clips': R.tl, 'cuts': R.cuts, 'total': round(total, 2), 'scrolls': R.scrolls}, indent=1))
        await page.close(); await ctx.close(); await br.close()
        print('recorded', round(total, 1), 's', 'after cuts', round(total - sum(b - a for a, b in R.cuts), 1), 's; scrolls by scene', R.scrolls)

asyncio.run(main())
