const {chromium}=require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const runtime=path.resolve(__dirname,'../application/.runtime');
const qa=path.join(runtime,'oidc-qa');fs.mkdirSync(qa,{recursive:true});
function otp(secret){
 const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';
 for(const char of secret.toUpperCase().replace(/[^A-Z2-7]/g,''))bits+=alphabet.indexOf(char).toString(2).padStart(5,'0');
 const bytes=[];for(let i=0;i+8<=bits.length;i+=8)bytes.push(parseInt(bits.slice(i,i+8),2));
 const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
 const mac=crypto.createHmac('sha256',Buffer.from(bytes)).update(counter).digest(),offset=mac[mac.length-1]&15;
 return String((mac.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}
const results=[];let step='start';
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 try{
  for(const account of (process.argv.slice(2).length?process.argv.slice(2):['u-alice'])){
   const context=await browser.newContext({ignoreHTTPSErrors:true}),page=await context.newPage();page.setDefaultTimeout(15000);
   step=account+':login';await page.goto('https://localhost:8443/oidc/login');
   await page.locator('#username').fill(account);
   await page.locator('#password').fill(fs.readFileSync(path.join(runtime,'infra/secrets/login_'+account),'utf8').trim());
   await page.locator('#kc-login').click();await page.waitForLoadState('networkidle');
   step=account+':mfa';
   const secretFile=path.join(qa,account+'.otp');
   if(await page.locator('#totpSecret').count()){
    await page.locator('#mode-manual').click();
    const secret=(await page.locator('#kc-totp-secret-key').innerText()).replace(/\s/g,'');fs.writeFileSync(secretFile,secret,{mode:0o600});
    await page.locator('#totp').fill(otp(secret));
    await page.locator('#userLabel').fill('Banc de validation local');
    await page.locator('#saveTOTPBtn').click();
   }else if(await page.locator('#otp').count()){
    await page.locator('#otp').fill(otp(fs.readFileSync(secretFile,'utf8')));await page.locator('#kc-login').click();
   }
   await page.waitForLoadState('networkidle');
   step=account+':session';
   const result=await page.evaluate(async()=>{const r=await fetch('/api/session');if(!r.ok)return{status:r.status};const s=await r.json();return{authenticated:s.authenticated,role:s.user?.role,auth:s.environment?.auth};});
   results.push({account,...result});
   if(!result.authenticated||result.auth!=='oidc'){
    results.push(await page.evaluate(()=>({path:location.pathname,detail:location.pathname==='/oidc/callback'?JSON.parse(document.body.innerText).detail:undefined,headings:[...document.querySelectorAll('h1,h2')].map(n=>n.textContent.trim()),errors:[...document.querySelectorAll('.kc-feedback-text,[aria-live],.pf-v5-c-alert__title,#input-error-otp-code')].map(n=>n.textContent.trim())})));
    throw new Error('OIDC session absent');
   }
   const workspace=await page.evaluate(async()=>{const r=await fetch('/api/workspace');return{status:r.status};});
   if(workspace.status!==200)throw new Error('Workspace refused');
   await page.screenshot({path:path.join(__dirname,'captures','oidc-'+account+'.png'),fullPage:true});
   await context.close();
  }
 }finally{await browser.close();}
})().catch(()=>{results.push({failure:true,step});process.exitCode=1;}).finally(()=>{
 fs.writeFileSync(path.join(__dirname,'captures','verification-oidc-live.json'),JSON.stringify({results,limits:'Comptes fictifs, MFA enrôlée sur le banc ; navigateur de test accepte la CA locale. Aucun secret capturé.'},null,2));
 console.log(JSON.stringify(results));
});
