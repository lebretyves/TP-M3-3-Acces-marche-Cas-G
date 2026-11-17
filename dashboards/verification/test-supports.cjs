const {chromium,webkit,devices}=require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
const url='http://127.0.0.1:8771';
const out=path.join(__dirname,'captures');
const report={scope:'Émulation navigateur, pas appareils physiques',checks:[],failures:[]};
(async()=>{
 for(const [engineName,engine,executablePath,profiles] of [
  ['Chromium',chromium,'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',[
   ['Android portrait',{...devices['Pixel 5']}],['Android paysage',{...devices['Pixel 5'],viewport:{width:851,height:393},screen:{width:851,height:393}}]
  ]],
  ['WebKit',webkit,'C:/Users/lebre/AppData/Local/ms-playwright/webkit-2248/Playwright.exe',[
   ['iPhone paysage',{...devices['iPhone 13 landscape']}],['Tablette paysage',{...devices['iPad Mini landscape']}],['Bureau WebKit',{viewport:{width:1440,height:1000}}]
  ]]
 ]){
  const browser=await engine.launch({headless:false,executablePath,timeout:20000});
  try{
   for(const [profileName,options] of profiles){
    const context=await browser.newContext({...options,reducedMotion:'reduce'}),page=await context.newPage();
    page.on('pageerror',e=>report.failures.push({profile:profileName,error:e.message}));
    await page.goto(url,{waitUntil:'networkidle'});
    for(const role of ['user','clinician','employer','support','admin']){
     await page.selectOption('#role-select',role);
     const size=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,title:document.querySelector('#content h1')?.textContent.trim()}));
     if(size.scroll>size.width+1||!size.title)report.failures.push({profile:profileName,role,size});
     await page.locator('#account').click();
     if(!await page.locator('#dialog').isVisible())report.failures.push({profile:profileName,role,error:'Account dialog absent'});
     await page.locator('#dialog-close').click();
     report.checks.push({engine:engineName,profile:profileName,role,...size});
     if(role==='user')await page.screenshot({path:path.join(out,`user-${profileName.replaceAll(' ','-')}.png`),fullPage:true});
    }
    await context.close();
   }
  }finally{await browser.close();}
 }
 fs.writeFileSync(path.join(out,'verification-supports.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({checks:report.checks.length,failures:report.failures}));
 if(report.failures.length)process.exitCode=1;
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
