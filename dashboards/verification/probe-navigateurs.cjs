const { chromium, webkit } = require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
(async () => {
  for(const [name, engine, executablePath] of [
    ['Chromium', chromium, 'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'],
    ['WebKit', webkit, 'C:/Users/lebre/AppData/Local/ms-playwright/webkit-2248/Playwright.exe']
  ]) {
    let browser;
    try {
      browser=await engine.launch({headless:false,executablePath,timeout:20000});
      const page=await browser.newPage();
      await page.goto('http://127.0.0.1:8771',{timeout:15000});
      await page.evaluate(()=>document.fonts.ready);
      console.log(JSON.stringify({engine:name,version:browser.version(),title:await page.title(),font:await page.evaluate(()=>document.fonts.check('italic 800 24px Saira'))}));
    } catch(error) { console.log(JSON.stringify({engine:name,error:error.message})); process.exitCode=1; }
    finally { if(browser) await browser.close(); }
  }
})().catch(error=>{ console.error(error.message); process.exitCode=1; });
