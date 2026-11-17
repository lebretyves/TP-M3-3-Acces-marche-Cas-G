const {chromium} = require('E:/Archive_Web_design/studio-createur-sites/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const out=path.join(__dirname,'evaluation-captures'); fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8771'); await page.evaluate(()=>document.fonts.ready);
 const report=[];
 for(const width of [1440,1024,768,375,320]){
   await page.setViewportSize({width,height:width>900?1000:900});
   for(const role of ['user','clinician','employer','support','admin']){
     await page.selectOption('#role-select',role);
     await page.screenshot({path:path.join(out,`${role}-${width}.png`),fullPage:true});
     report.push({role,width,stats:await page.evaluate(()=>({documentWidth:document.documentElement.scrollWidth,viewport:innerWidth,heading:document.querySelector('h1')?.innerText,smallTargets:[...document.querySelectorAll('button,input,select,a')].filter(el=>el.getClientRects().length).map(el=>({text:(el.innerText||el.getAttribute('aria-label')||el.id).slice(0,80),h:Math.round(el.getBoundingClientRect().height),w:Math.round(el.getBoundingClientRect().width)})).filter(r=>r.h<30||r.w<30)}))});
   }
 }
 await page.setViewportSize({width:1440,height:1000});await page.selectOption('#role-select','user');await page.locator('[data-period="month"]').click();await page.screenshot({path:path.join(out,'user-month.png'),fullPage:true});
 await page.locator('[data-page="shares"]').click().catch(()=>{});report.push({userNavigation:await page.locator('#navigation').innerText(),userButtons:await page.locator('#content button').allTextContents()});
 await page.selectOption('#role-select','clinician');await page.locator('[data-action="patient"]').first().click();await page.screenshot({path:path.join(out,'clinician-patient.png'),fullPage:true});report.push({clinician:await page.locator('#content').innerText(),tabs:await page.locator('[data-tab]').allTextContents()});
 await page.setViewportSize({width:375,height:900});await page.selectOption('#role-select','support');await page.locator('[data-action="ticket-select"]').first().click();await page.screenshot({path:path.join(out,'support-detail-375.png'),fullPage:true});
 fs.writeFileSync(path.join(out,'inspection.json'),JSON.stringify({report,errors},null,2));console.log(JSON.stringify({report,errors}));await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
