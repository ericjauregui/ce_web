// Run with Node + Playwright installed. The browser composites ORIGINAL portraits;
// GPT Images supplies only backdrop.png. No face retouching or regeneration.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.CE_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const data = (filename, mime) => `data:${mime};base64,${fs.readFileSync(path.join(root, filename)).toString('base64')}`;
const escape = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
(async () => {
  const team = JSON.parse(fs.readFileSync(path.join(root, 'catalog/team.json')));
  const browser = await chromium.launch({headless:true, ...(process.env.CE_CHROME_PATH ? {executablePath:process.env.CE_CHROME_PATH} : {channel:'chrome'})});
  try {
    const page = await browser.newPage({viewport:{width:1200,height:630},deviceScaleFactor:1});
    for (const member of team.members) {
      if (!member.social_image || !member.photo) continue;
      const name = escape(member.name);
      const html = `<!doctype html><html><head><meta charset="utf-8"><style>
      @font-face{font-family:Lato;src:url('${data('static/vendor/fonts/lato-400-latin.woff2','font/woff2')}')}
      @font-face{font-family:Playfair;src:url('${data('static/vendor/fonts/playfair-display-latin.woff2','font/woff2')}')}
      *{box-sizing:border-box}body{margin:0;width:1200px;height:630px;background:#090909 url('${data('static/assets/team-social/backdrop.png','image/png')}') center/cover;color:#eee1c2;font-family:Lato,sans-serif;display:flex;align-items:center;gap:66px;padding:70px 90px}
      .portrait{flex:0 0 auto;width:282px;height:282px;padding:5px;border-radius:50%;background:linear-gradient(140deg,#f2dd9e,#99753b,#ffedbb,#977034);box-shadow:0 0 0 9px #0b0a08,0 0 0 10px #b99a5255;overflow:hidden}
      .crop{width:100%;height:100%;border:6px solid #15120e;border-radius:50%;overflow:hidden}
      .portrait img{width:100%;height:100%;object-fit:cover;object-position:${escape(member.photo_position || '50% 50%')};transform:scale(${Number(member.photo_scale) || 1});transform-origin:${escape(member.photo_position || '50% 50%')}}
      .copy{flex:1;min-width:0}.brand{display:flex;align-items:center;gap:17px;color:#dcc28a;letter-spacing:3px;text-transform:uppercase;font-size:15px;margin-bottom:32px}.brand img{width:350px;height:84px;object-fit:contain}
      h1{font:500 55px/1.12 Playfair,serif;margin:0 0 20px;color:#f3e7c9}p{font-size:24px;color:#d6b766;margin:0}.rule{width:72px;height:1px;background:#a98b49;margin:29px 0 23px}.footer{font-size:17px;color:#bfb299;letter-spacing:.5px}
      </style></head><body><div class="portrait"><div class="crop"><img src="${data('static/team/'+member.photo,'image/jpeg')}" alt="${name}"></div></div><div class="copy"><div class="brand"><img src="${data('static/assets/ce_logo_full.png','image/png')}" alt="${escape(team.company)}"></div><h1>${name}</h1><p>${escape(member.title)}</p><div class="rule"></div><div class="footer">Wholesale Jewelry • Los Angeles • California • Since 1992</div></div></body></html>`;
      await page.setContent(html);
      await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode())); });
      const output = path.join(root,'static',member.social_image);
      fs.mkdirSync(path.dirname(output),{recursive:true});
      await page.screenshot({path:output,type:'jpeg',quality:92});
      console.log(path.relative(root,output));
    }
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exit(1)});
