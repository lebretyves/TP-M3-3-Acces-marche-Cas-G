const {chromium}=require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 try{
  const page=await browser.newPage({ignoreHTTPSErrors:true});page.setDefaultTimeout(10000);
  await page.goto('https://localhost:8443/oidc/login');
  console.log(JSON.stringify({stage:'login',headings:await page.locator('h1,h2').allTextContents(),inputs:await page.locator('input').evaluateAll(ns=>ns.map(n=>({id:n.id,name:n.name,type:n.type})))}));
  if(await page.locator('#username').count()){
   await page.locator('#username').fill('u-alice');
   await page.locator('#password').fill(fs.readFileSync(path.join(__dirname,'../application/.runtime/infra/secrets/login_u-alice'),'utf8').trim());
   await page.locator('#kc-login').click();
   await page.waitForLoadState('networkidle');
   console.log(JSON.stringify({stage:'after_password',headings:await page.locator('h1,h2').allTextContents(),inputs:await page.locator('input').evaluateAll(ns=>ns.map(n=>({id:n.id,name:n.name,type:n.type}))),links:await page.locator('a').evaluateAll(ns=>ns.map(n=>({id:n.id,text:n.textContent.trim()})).filter(n=>n.id||n.text))}));
  }
 }finally{await browser.close();}
})().catch(()=>{console.error('OIDC probe failed; no credentials or URLs logged.');process.exitCode=1;});
