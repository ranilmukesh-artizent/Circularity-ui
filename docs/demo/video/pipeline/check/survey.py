"""Survey every screen the new demo needs at 1440x900: how many screens tall it is, and a viewport shot.
python survey.py [user]"""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

D = Path(__file__).resolve().parent
OUT = D / 'shots'; OUT.mkdir(exist_ok=True)
ROOT = 'file:///C:/repos/astra-prism-DI/ayush-ui/Circularity-ui/'
APP = ROOT + 'index.html?presenter=0'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
USER = sys.argv[1] if len(sys.argv) > 1 else 'admin'
ROUTES = ['home', 'product/received', 'product/asset/RT-1048', 'product/RT-1048/overview'] + \
    [f'product/RT-1048/stage/{n}' for n in range(1, 11)] + ['product/RT-1048/full'] + \
    [f'integration/{t}' for t in ['overview', 'studio', 'map', 'tables', 'models']] + \
    ['analytics', 'analytics/predicted', 'orchestration/run']

MEASURE = r"""()=>{const vh=innerHeight;const se=document.scrollingElement;
 const inner=[...document.querySelectorAll('#view, #view *')].filter(x=>x.scrollHeight>x.clientHeight+40&&/auto|scroll/.test(getComputedStyle(x).overflowY)&&x.clientHeight>200)
  .map(x=>({tag:x.tagName+(x.id?'#'+x.id:'')+(x.className&&typeof x.className=='string'?'.'+x.className.split(' ')[0]:''),screens:+(x.scrollHeight/x.clientHeight).toFixed(2)})).slice(0,4);
 const hs=[...document.querySelectorAll('#view h1,#view h2,#view h3')].map(h=>h.textContent.trim().slice(0,60)).filter(Boolean).slice(0,14);
 const imgs=[...document.querySelectorAll('#view img')].map(i=>({src:i.getAttribute('src').slice(0,60),ok:i.complete&&i.naturalWidth>0,vis:i.getBoundingClientRect().top<vh})).slice(0,6);
 return {hash:location.hash,pageScreens:+(se.scrollHeight/vh).toFixed(2),inner,headings:hs,imgs}}"""

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True, args=['--disable-ipc-flooding-protection', '--hide-scrollbars', '--allow-file-access-from-files'])
        ctx = await br.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='light')
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(APP); await page.evaluate('()=>localStorage.clear()'); await page.reload()
        await page.wait_for_selector('#si-id', timeout=15000)
        await page.screenshot(path=str(OUT / '00-signin.png'))
        await page.fill('#si-id', USER); await page.fill('#si-pw', 'password')
        await page.click('#siForm button[type=submit], #siForm .btn.pri'); await asyncio.sleep(2)
        res = []
        for i, r in enumerate(ROUTES, 1):
            await page.evaluate('h=>{location.hash="#/"+h}', r); await asyncio.sleep(1.6)
            await page.evaluate('()=>scrollTo(0,0)'); await asyncio.sleep(0.2)
            m = await page.evaluate(MEASURE); m['route'] = r; res.append(m)
            await page.screenshot(path=str(OUT / f'{i:02d}-{r.replace("/", "_")}.png'))
            print(f"{r:32s} page={m['pageScreens']:<5} inner={m['inner']} -> {m['hash']}", flush=True)
        # framework landing
        await page.goto(ROOT + 'framework/index.html'); await asyncio.sleep(1.5)
        m = await page.evaluate('()=>({screens:+(document.scrollingElement.scrollHeight/innerHeight).toFixed(2),h:[...document.querySelectorAll("h1,h2,h3")].map(h=>h.textContent.trim().slice(0,70)).slice(0,12)})')
        print('framework', m); await page.screenshot(path=str(OUT / '99-framework.png'), full_page=True)
        (D / 'survey.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
        print('page errors:', errs[:5])
        await br.close()

asyncio.run(main())
