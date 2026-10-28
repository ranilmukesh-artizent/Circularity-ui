"""Walk the CXO demo flow headless at 1440x900, screenshot each beat into shots3/, report page errors and page heights."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

D = Path(__file__).resolve().parent; OUT = D / 'shots3'; OUT.mkdir(exist_ok=True)
for f in OUT.glob('*.png'): f.unlink()
APP = 'file:///C:/repos/astra-prism-DI/ayush-ui/Circularity-ui/index.html?presenter=0'
ONLY = sys.argv[1] if len(sys.argv) > 1 else ''
N = [0]

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True, args=['--disable-ipc-flooding-protection', '--hide-scrollbars'])
        page = await (await br.new_context(viewport={'width': 1440, 'height': 900}, color_scheme='light')).new_page()
        errs = []; page.on('pageerror', lambda e: errs.append(str(e)))
        async def shot(name):
            N[0] += 1; h = await page.evaluate('()=>+(document.scrollingElement.scrollHeight/innerHeight).toFixed(2)')
            await page.screenshot(path=str(OUT / f'{N[0]:02d}-{name}.png')); print(f'{N[0]:02d} {name:28s} screens={h} {await page.evaluate("()=>location.hash")}', flush=True)
        async def hash(h): await page.evaluate('h=>{location.hash=h}', h); await asyncio.sleep(1.4); await page.evaluate('()=>scrollTo(0,0)')
        async def sign(u):
            if await page.locator('summary.acchip').count():
                await page.click('summary.acchip'); await asyncio.sleep(.3); await page.click('[data-act="signOut"]'); await asyncio.sleep(.8)
            await page.wait_for_selector('#si-id'); await page.fill('#si-id', u); await page.fill('#si-pw', 'password')
            await page.click('#siForm button[type=submit], #siForm .btn.pri'); await asyncio.sleep(1.6)
        async def ask(q):
            if not await page.locator('#askp:visible').count(): await page.click('#afAskBtn'); await asyncio.sleep(.5)
            await page.fill('#afq', q); await page.keyboard.press('Enter'); await asyncio.sleep(2.8)
        await page.goto(APP); await page.evaluate('()=>localStorage.clear()'); await page.reload()
        if ONLY in ('', 'case'):
            await sign('ops')
            await hash('#/product/received'); await shot('received')
            await hash('#/product/asset/RT-1048'); await shot('asset')
            await page.click('#view img[src*="assets/products/"]'); await asyncio.sleep(.6); await shot('lightbox'); await page.keyboard.press('Escape')
            await hash('#/product/RT-1048/overview'); await shot('overview')
            await hash('#/product/RT-1048/stage/5'); await shot('stage5')
            await hash('#/product/RT-1048/stage/6'); await shot('stage6')
            await page.click('#view [data-act="cxExplain"]'); await asyncio.sleep(.8); await shot('explain')
            await page.hover('#cxX .cxd >> nth=0'); await asyncio.sleep(.3)
            await page.locator('#cx-sc-cost').fill('130'); await page.dispatch_event('#cx-sc-cost', 'input'); await asyncio.sleep(.6); await shot('explain-cost130')
            await page.click('#cxX [data-act="cxPreset"][data-arg="demand"]'); await asyncio.sleep(.6); await shot('explain-demand')
            print('  impact:', (await page.inner_text('#cxImpact')).replace('\n', ' | ')[:300])
            await page.click('#cxX [data-act="cxPreset"][data-arg="reset"]'); await asyncio.sleep(.3); await page.click('#cxX [data-act="cxClose"]'); await asyncio.sleep(.6)
            sub = page.locator('#view button:has-text("Submit RT-1048 for review")')
            print('  submit buttons', await sub.count())
            if await sub.count(): await sub.first.click(); await asyncio.sleep(1.2); await shot('submitted')
            await sign('approver')
            await hash('#/product/RT-1048/stage/7'); await shot('stage7')
            ap = page.locator('#view button:has-text("Approve")'); print('  approve buttons', await ap.count())
            await ap.first.click(); await asyncio.sleep(1.0); await shot('approve-modal')
            cb = page.locator('#modal input[type=checkbox]')
            for i in range(await cb.count()): await cb.nth(i).check()
            await page.click('#modal [data-act="confirmApprove"]'); await asyncio.sleep(2.5)
            await hash('#/product/RT-1048/stage/8'); await shot('stage8')
            print('  stage8 buttons:', [t.strip()[:50] for t in await page.locator('#view button, #jgGuide button').all_inner_texts()][:40])
        if ONLY in ('', 'fabric'):
            await sign('admin')
            await hash('#/integration/overview'); await shot('fab-overview')
            await hash('#/integration/map'); await shot('fab-map')
            await hash('#/integration/models'); await shot('fab-models')
            await hash('#/integration/studio'); await ask('Draft a workflow that brings repair and bench-test results in from the MRO workshop every 15 minutes'); await shot('wf-draft')
            await page.locator('#askp [data-act="afDo"]:has-text("Accept")').first.click(); await asyncio.sleep(1.2); await shot('wf-reveal-mid'); await asyncio.sleep(3.5); await shot('wf-revealed')
            await ask('Run it every five minutes, and flag any unit that fails its bench test'); await shot('wf-edit-card')
            ap = page.locator('#askp [data-act="afDo"]:has-text("Apply to the canvas")'); print('  apply buttons', await ap.count())
            if await ap.count(): await ap.first.click(); await asyncio.sleep(2); await shot('wf-edited')
            await page.keyboard.press('Escape')
            await hash('#/analytics/predicted'); await shot('analytics')
            await page.evaluate('''()=>{const h=[...document.querySelectorAll('#view h2,#view h3')].find(x=>x.textContent.trim().startsWith('Predicted vs actual'));h.parentElement.querySelector('button').click()}'''); await asyncio.sleep(1.5)
            chip = page.locator('#askp button:has-text("What changed and why")')
            if await chip.count(): await chip.first.click(); await asyncio.sleep(3)
            await shot('analytics-agent')
        print('page errors:', errs[:6])
        await br.close()

asyncio.run(main())
