const { chromium } = require('E:/Archive_Web_design/studio-createur-sites/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const TARGET_URL = 'http://127.0.0.1:8771';
const out = path.resolve(__dirname, 'captures');
fs.mkdirSync(out, {recursive:true});
(async () => {
  const browser = await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
  const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const page = await context.newPage();
  const failures = [], checks = [], errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => { if(r.status() >= 400 && !r.url().endsWith('favicon.ico')) requests.push({url:r.url(),status:r.status()}); });
  try {
    await page.goto(TARGET_URL, {waitUntil:'networkidle'});
    await page.locator('#content h1').waitFor({state:'visible',timeout:15000});
    await page.evaluate(() => document.fonts.ready);
    for (const width of [1440,1024,768,390,360,320]) {
      await page.setViewportSize({width,height:width===1440?1000:844});
      for(const role of ['user','clinician','employer','support','admin']) {
        await page.selectOption('#role-select', role);
        await page.locator('#content h1').waitFor({state:'visible'});
        const state=await page.evaluate(()=>({title:document.querySelector('#content h1')?.textContent.trim(),width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,content:document.querySelector('#content').innerText.length,headings:[...document.querySelectorAll('#content h1')].length}));
        if(state.scrollWidth>state.width+1) failures.push({role,width,problem:'page horizontal overflow',state});
        if(state.content<160 || state.headings!==1) failures.push({role,width,problem:'incomplete page',state});
        checks.push({role,width,...state});
        await page.screenshot({path:path.join(out,`${role}-${width}.png`),fullPage:true});
        if(width===1440) {
          const nav=await page.locator('#navigation [data-page]').evaluateAll(nodes=>nodes.map(n=>({page:n.dataset.page,label:n.textContent.trim()})));
          for(const item of nav) {
            await page.locator(`#navigation [data-page="${item.page}"]`).click();
            await page.locator('#content h1').waitFor({state:'visible'});
            const content=await page.locator('#content').innerText();
            if(content.length<100) failures.push({role,page:item.page,problem:'empty navigation page'});
            checks.push({role,page:item.page,label:item.label,characters:content.length});
          }
        } else if (width <= 900) {
          await page.locator('#open-menu').click();
          if(await page.locator('#open-menu').getAttribute('aria-expanded')!=='true') failures.push({role,width,problem:'mobile menu not opened'});
          await page.keyboard.press('Escape');
          if(await page.locator('#open-menu').getAttribute('aria-expanded')!=='false') failures.push({role,width,problem:'mobile menu not closed with Escape'});
        }
      }
    }
    const report={target:TARGET_URL,checkedAt:new Date().toISOString(),checks,failures,errors,requests};
    fs.writeFileSync(path.join(out,'verification-navigation.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({checks:checks.length,failures,errors,requests}));
    if(failures.length||errors.length||requests.length) process.exitCode=1;
  } finally { await browser.close(); }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
