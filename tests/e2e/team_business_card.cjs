// CE_TEAM_BASE_URL=http://127.0.0.1:5088 node tests/e2e/team_business_card.cjs
const { chromium, webkit } = require(process.env.CE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.CE_TEAM_BASE_URL || 'http://127.0.0.1:5088';
const output = path.resolve('.test-artifacts/team-card');
fs.mkdirSync(output,{recursive:true});
(async () => {
  for (const [name, type, launch] of [['chromium',chromium,{channel:'chrome'}],['webkit',webkit,process.env.CE_WEBKIT_PATH ? {executablePath:process.env.CE_WEBKIT_PATH} : {}]]) {
    const browser = await type.launch({headless:true,...launch});
    try {
      const context = await browser.newContext();
      const page = await context.newPage();
      const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      for (const width of [320,390,768,1280]) {
        await page.setViewportSize({width,height:900});
        for (const slug of ['miguel','giancarlo','ari']) {
          await page.goto(`${base}/team/${slug}`);
          await page.evaluate(()=>document.fonts.ready);
          assert.equal(await page.locator('h1').count(),1);
          assert.equal(await page.locator('#navSearchForm').count(),1);
          assert.equal(await page.locator('#cartLink').count(),1);
          assert.equal(await page.locator('.latest-videos-section').count(),0);
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}: overflow ${slug} ${width}`);
          assert.ok(await page.locator('.dbc-portrait').evaluate(i=>i.complete&&i.naturalWidth>0));
          assert.equal(await page.locator('#contactQr').evaluate(e=>e.open),width>=768);
          if(width<768){
            await page.locator('#contactQr summary').click();
            assert.equal(await page.locator('#contactQr').evaluate(e=>e.open),true);
            assert.ok(await page.locator('.dbc-qr-frame img').isVisible());
          }
          const og=await page.locator('meta[property="og:image"]').getAttribute('content');
          assert.ok(og.includes(`team-social/${slug}.jpg`));
          const asset=new URL(og);assert.equal((await page.request.get(base+asset.pathname+asset.search)).status(),200);
          if(width===390||width===1280)await page.screenshot({path:path.join(output,`${name}-${slug}-${width}.png`),fullPage:true});
        }
      }
      // Native sharing passes the canonical member link, without tracking query parameters.
      await page.goto(`${base}/team/ari?utm_source=test`);
      await page.evaluate(()=>{
        window.shared=null;
        Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{window.shared=data}});
      });
      await page.locator('#shareCard').click();
      const shared=await page.evaluate(()=>window.shared);
      assert.ok(shared.url.endsWith('/team/ari'));
      assert.ok(shared.title.includes('Ari Guel'));
      assert.equal(await page.locator('#shareFallback').isVisible(),false);
      // User dismissal is quiet.
      await page.evaluate(()=>Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{throw new DOMException('Cancelled','AbortError')}}));
      await page.locator('#shareCard').click();
      assert.equal(await page.locator('#shareFallback').isVisible(),false);
      assert.equal(await page.locator('#shareCard').isDisabled(),false);
      // Unsupported / blocked native sharing opens a usable copy fallback.
      await page.evaluate(()=>Object.defineProperty(navigator,'share',{configurable:true,value:undefined}));
      await page.locator('#shareCard').click();
      assert.equal(await page.locator('#shareFallback').isVisible(),true);
      await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.copied=value}}}));
      await page.locator('#copyCardLink').click();
      assert.equal(await page.locator('#shareStatus').textContent(),'Card link copied.');
      assert.ok((await page.evaluate(()=>window.copied)).endsWith('/team/ari'));
      await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('Denied')}}}));
      await page.locator('#copyCardLink').click();
      assert.match(await page.locator('#shareStatus').textContent(),/Select and copy/);
      assert.equal(await page.locator('#shareLink').evaluate(e=>e.selectionEnd-e.selectionStart), (await page.locator('#shareLink').inputValue()).length);
      await page.goto(`${base}/team/ari`);
      await page.evaluate(()=>Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{throw new Error('Blocked')}}));
      await page.locator('#shareCard').click();
      assert.equal(await page.locator('#shareFallback').isVisible(),true);
      // Resizing restores the always-visible desktop QR.
      await page.setViewportSize({width:390,height:844});
      await page.waitForFunction(()=>!document.getElementById('contactQr').open);
      await page.setViewportSize({width:1280,height:900});
      await page.waitForFunction(()=>document.getElementById('contactQr').open);
      // Native links and QR remain available without JavaScript.
      const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});
      const np=await nojs.newPage();await np.goto(`${base}/team/ari`);
      assert.ok(await np.locator('a[href$="contact.vcf"]').isVisible());
      assert.ok(await np.locator('.dbc-qr-frame img').isVisible());
      assert.equal(await np.locator('#shareCard').isVisible(),false);
      await nojs.close();
      assert.deepEqual(errors,[]);
      console.log(`${name}: all members, 4 widths, native share/cancel/error, copy/denied, resize, no-JS passed`);
      await context.close();
    } finally {await browser.close()}
  }
})().catch(e=>{console.error(e);process.exit(1)});
