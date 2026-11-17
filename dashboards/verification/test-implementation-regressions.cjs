const {chromium}=require('E:/Archive_Web_design/studio-createur-sites/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const b=await chromium.launch({executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',headless:true});
 const p=await b.newPage({viewport:{width:1440,height:1000}}),errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 const action=async name=>p.locator(`[data-action="${name}"]`).first().click();
 const submit=async()=>p.locator('#dialog-submit').click();
 await p.goto('http://127.0.0.1:8771');
 await p.locator('#role-select').selectOption('clinician');
 await p.locator('#navigation [data-page="help"]').click();
 await action('help-new');await p.locator('[name="title"]').fill('Affichage technique');await p.locator('[name="body"]').fill('Une rubrique ne se charge pas dans le scénario.');await submit();
 await p.locator('#role-select').selectOption('support');await p.locator('[data-action="ticket-select"]').last().click();
 assert.match(await p.locator('.ticket-detail').innerText(),/Aucun appareil ni dossier patient/);
 assert.equal(await p.locator('.ticket-detail [data-action="support-replace"]').count(),0);
 await action('ticket-reply');await p.locator('[name="reply"]').fill('Le chargement du service a été vérifié.');await submit();await action('ticket-close');
 assert.match(await p.locator('.ticket-detail').innerText(),/Résolu/);
 console.log('PASS ticket soignant sans appareil patient, réponse et clôture');
 await p.locator('#role-select').selectOption('admin');await p.locator('#navigation [data-page="accounts"]').click();
 await action('account-create');await p.locator('[name="id"]').fill('QA-NEW');await submit();
 const row=p.locator('tbody tr').filter({hasText:'QA-NEW'});
 for(const expected of ['Suspendu','Actif']){await row.locator('[data-action="account-toggle"]').click();await p.locator('[name="reason"]').fill('Vérification du scénario');await submit();assert.match(await row.innerText(),new RegExp(expected));}
 console.log('PASS compte neuf sans session : suspension puis réactivation');
 await p.reload();await p.locator('#role-select').selectOption('support');
 await p.locator('[data-action="ticket-select"][data-id="1"]').click();assert(await p.locator('[data-action="support-replace"]').isDisabled());
 await p.locator('[data-action="ticket-select"][data-id="0"]').click();await action('support-replace');await p.locator('#dialog input[type="checkbox"]').check();await submit();
 await action('calibrate');for(let i=0;i<3;i++){const checkbox=p.locator('#dialog input[type="checkbox"]');if(await checkbox.count())await checkbox.check();await submit();}
 await action('maintenance');assert.match(await p.locator('#content').innerText(),/Calibration C-03 vérifiée/);
 await p.locator('#role-select').selectOption('user');await p.locator('#navigation [data-page="device"]').click();
 assert.match(await p.locator('#content').innerText(),/Vérifiée · C-03/);assert.doesNotMatch(await p.locator('#content').innerText(),/Vérifiée · Non vérifiée/);
 console.log('PASS diagnostic fermé, remplacement et calibration C-03 cohérents');
 assert.deepEqual(errors,[]);console.log('PASS aucune erreur JavaScript');await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
