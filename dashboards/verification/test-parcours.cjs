const { chromium, webkit, devices } = require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const TARGET_URL='http://127.0.0.1:8771';
const out=path.join(__dirname,'captures');
fs.mkdirSync(out,{recursive:true});
const results=[], errors=[];
function assert(value,message){if(!value)throw new Error(message);}
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',timeout:20000});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 page.on('pageerror',e=>errors.push(e.message));
 const action=name=>page.locator(`[data-action="${name}"]`).first();
 const close=()=>page.locator('#dialog-close').click();
 try {
  await page.goto(TARGET_URL,{waitUntil:'networkidle'});
  await page.locator('[data-period="week"]').click();
  assert((await page.locator('#content').innerText()).includes('Du 8 au 14 novembre 2026'),'Week period not updated');
  await page.locator('[data-period="month"]').click();
  assert((await page.locator('#content').innerText()).includes('Du 16 octobre au 14 novembre 2026'),'Month period not updated');
  results.push('Période commune Jour/Semaine/Mois');
  await page.locator('#navigation').getByText('Mes partages',{exact:true}).click();
  const oldRows=await page.locator('#content tbody tr').count();
  await action('share-new').click();
  await page.locator('#dialog input[name=start]').fill('2026-11-09');
  await page.locator('#dialog input[name=end]').fill('2026-11-12');
  await page.locator('#dialog input[name=moves]').uncheck();
  await page.locator('#dialog-submit').click();
  assert(await page.locator('#content tbody tr').count()===oldRows+1,'Share not created');
  await page.locator('#content tbody tr').last().getByRole('button',{name:'Révoquer',exact:true}).click();
  await page.locator('#dialog-submit').click();
  assert((await page.locator('#content tbody tr').last().innerText()).includes('Révoqué'),'Share not revoked');
  results.push('Création et révocation de partage fictif');
  await page.locator('#navigation').getByText('Ma souris',{exact:true}).click();
  await action('calibrate').click();
  for(let i=0;i<2;i++){await page.locator('#dialog input[type=checkbox]').check();await page.locator('#dialog-submit').click();}
  assert((await page.locator('#dialog').innerText()).includes('Résultat simulé'),'Calibration result absent');
  await page.locator('#dialog-submit').click();
  results.push('Calibration simulée en trois étapes');
  await page.selectOption('#role-select','clinician');
  const expired=await page.locator('#patient-table tbody tr').last().locator('td').nth(1).innerText();
  assert(!expired.includes('nov.')&&!expired.includes('Valide'),'Measurement metadata remains in expired relation');
  await action('patient').click();
  assert(await page.locator('[data-action="export-user"]').count()===0,'Clinician export must be absent');
  await action('compare').click();
  assert(await page.locator('[data-comparison]').count()===2,'Comparison period selectors absent');
  await page.locator('[data-comparison="B"]').selectOption('day');
  assert((await page.locator('#comparison-caution').innerText()).includes('durées'),'Comparison duration warning absent');
  await close();
  results.push('Dossier autorisé, comparaison et restrictions soignant');
  await page.selectOption('#role-select','employer');
  await page.locator('[data-org-status]').first().selectOption('Réalisée');
  assert(await page.locator('[data-org-status]').first().inputValue()==='Réalisée','Employer status unchanged');
  await page.locator('#navigation').getByText('Historique',{exact:true}).click();
  assert((await page.locator('#content').innerText()).includes('Réalisée'),'Employer history missing status');
  results.push('Avancement et historique des recommandations');
  await page.selectOption('#role-select','support');
  await action('ticket-close').click();
  assert((await page.locator('#toast').innerText()).includes('trois vérifications'),'Closure not guarded by checks');
  for(const name of ['connection','sensors','calibration']) await page.locator(`[data-check="${name}"]`).check();
  await action('ticket-close').click();
  assert((await page.locator('#content').innerText()).includes('Résolu'),'Ticket not resolved after checks');
  results.push('Clôture de ticket conditionnée aux vérifications');
  await page.selectOption('#role-select','admin');
  await action('alert').click();
  await page.locator('#dialog select[name=qualification]').selectOption('Incident confirmé');
  await page.locator('#dialog textarea[name=reason]').fill('Scénario de contrôle : événement fictif vérifié.');
  await page.locator('#dialog-submit').click();
  assert((await page.locator('#content').innerText()).includes('Incident confirmé'),'Incident qualification not saved');
  results.push('Qualification motivée d’un incident fictif');
  await page.locator('#navigation').getByText('Paramètres',{exact:true}).click();
  await page.locator('[data-setting=large]').check();
  await page.locator('[data-setting=contrast]').check();
  assert(await page.locator('html').evaluate(e=>e.classList.contains('large-text')&&e.classList.contains('high-contrast')),'Display preferences not applied');
  results.push('Préférences de lisibilité');
 } finally {await browser.close();}
 const safari=await webkit.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/webkit-2248/Playwright.exe',timeout:20000});
 try {
  for(const name of ['iPhone 13','iPad Mini']){
   const context=await safari.newContext({...devices[name],reducedMotion:'reduce'});
   const mobile=await context.newPage();mobile.on('pageerror',e=>errors.push(e.message));
   await mobile.goto(TARGET_URL,{waitUntil:'networkidle'});
   for(const role of ['user','clinician','employer','support','admin']){
    await mobile.selectOption('#role-select',role);
    const size=await mobile.evaluate(()=>({w:document.documentElement.clientWidth,s:document.documentElement.scrollWidth}));
    assert(size.s<=size.w+1,`${name} ${role} horizontal overflow`);
    await mobile.locator('#open-menu').click();
    await mobile.locator('#close-menu').click();
    await mobile.locator('#notifications').click();
    assert(await mobile.locator('#dialog').isVisible(),`${name} ${role} dialog not opened`);
    await mobile.locator('#dialog-close').click();
    await mobile.screenshot({path:path.join(out,`${role}-${name.replaceAll(' ','-')}-webkit.png`),fullPage:true});
    results.push(`WebKit ${name} : ${role}, menu et notifications`);
   }
   await context.close();
  }
 } finally {await safari.close();}
 assert(errors.length===0,JSON.stringify(errors));
 fs.writeFileSync(path.join(out,'verification-parcours.json'),JSON.stringify({target:TARGET_URL,results,errors,limits:'Émulation de formats et moteurs ; aucun essai sur iPhone, Android, tablette ou Mac physique.'},null,2));
 console.log(JSON.stringify({passed:results.length,results,errors}));
})().catch(e=>{fs.writeFileSync(path.join(out,'verification-parcours.json'),JSON.stringify({results,errors,failure:e.message},null,2));console.error(e.stack);process.exitCode=1;});
