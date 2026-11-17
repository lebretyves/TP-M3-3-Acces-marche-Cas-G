const {chromium}=require('C:/Users/lebre/.agents/skills/playwright/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
const report={checks:[],errors:[],limits:'Scénarios de présentation en mémoire ; aucune validation de sécurité serveur.'};
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Users/lebre/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(8000);
 page.on('pageerror',e=>report.errors.push(e.message));
 const action=(name)=>page.locator(`[data-action="${name}"]`).first();
 const nav=(name)=>page.locator(`#navigation [data-page="${name}"]`).click();
 const role=(name)=>page.selectOption('#role-select',name);
 const submit=()=>page.locator('#dialog-submit').click();
 const close=()=>page.locator('#dialog-close').click();
 const text=()=>page.locator('#content').innerText();
 const reset=()=>page.goto('http://127.0.0.1:8771',{waitUntil:'networkidle'});
 try{
  await reset();
  await nav('shares');await action('share-revoke').click();await submit();
  await role('clinician');
  assert(await page.locator('#patient-table [data-action="patient"][data-id="0"]').count()===0,'Révocation sans fermeture du dossier patient 01');
  assert((await page.locator('#patient-table tbody tr').first().innerText()).includes('Non accessible'),'Métadonnées encore visibles après révocation');
  await role('user');await nav('shares');await action('share-new').click();
  await page.locator('[name=start]').fill('2026-11-09');await page.locator('[name=end]').fill('2026-11-12');
  await page.locator('[name=pressure]').uncheck();await page.locator('[name=moves]').uncheck();await submit();
  await role('clinician');await page.locator('#patient-table [data-action="patient"][data-id="0"]').click();
  assert(await page.locator('.measure-unshared').count()===2,'Catégories non partagées affichées');
  await action('compare').click();
  assert((await page.locator('#comparison-values').innerText()).match(/Non partagé/g)?.length===4,'Comparaison hors catégories autorisées');
  await page.locator('[data-comparison="B"]').selectOption('day');
  assert((await page.locator('#comparison-values').innerText()).includes('Aucune donnée'),'Mesures du 14 accessibles hors partage 9–12');
  await close();report.checks.push('Révocation immédiate, catégories et dates effectives dans les graphiques et comparaisons');

  await reset();await role('clinician');await page.locator('[data-action="patient"][data-id="1"]').click();
  await page.locator('[data-tab="advice"]').click();await action('advice-edit').click();
  await page.locator('[name=title]').fill('Conseil spécifique Patient 02');await page.locator('[name=body]').fill('Texte de contrôle P02 uniquement');await submit();
  await action('advice-versions').click();assert((await page.locator('#dialog').innerText()).includes('Version 2'),'Nouvelle version absente');
  await page.locator('[data-action="document-version"][data-version="1"]').click();
  assert(!(await page.locator('#dialog').innerText()).includes('Texte de contrôle P02 uniquement'),'Ancienne version écrasée');await close();
  await page.locator('[data-tab="report"]').click();await action('report-edit').click();await page.locator('[name=body]').fill('Bilan spécifique P02 uniquement');await submit();
  await action('report-versions').click();assert(await page.locator('[data-action="document-version"]').count()===2,'Versions de bilan non conservées');await close();
  await role('user');await nav('advice');assert(!(await text()).includes('P02 uniquement'),'Conseil P02 exposé à User01');
  await action('report').click();assert(!(await page.locator('#dialog').innerText()).includes('P02 uniquement'),'Bilan P02 exposé à User01');await close();
  report.checks.push('Documents séparés par patient et versions antérieures consultables');

  await reset();await role('support');await action('support-update').click();await submit();
  await role('user');await nav('device');assert((await text()).includes('2.4.2'),'Mise à jour non reflétée dans la souris utilisateur');
  await page.locator('#notifications').click();assert((await page.locator('#dialog').innerText()).includes('calibration est nécessaire'),'Notification calibration absente');await close();
  await role('support');await page.locator('[data-action="ticket-select"][data-id="1"]').click();
  assert(await action('support-update').isDisabled(),'Mise à jour disponible avec diagnostic expiré');
  assert(!(await page.locator('.ticket-detail').innerText()).includes('Logiciel installé'),'Données diagnostic expiré encore visibles');
  await page.locator('[data-action="ticket-select"][data-id="2"]').click();assert(await action('calibrate').isDisabled(),'Calibration disponible avec diagnostic révoqué');
  await page.locator('[data-action="ticket-select"][data-id="0"]').click();await action('ticket-reply').click();await page.locator('[name=reply]').fill('Réponse technique de contrôle 2026');await submit();
  await role('user');await page.locator('#notifications').click();
  const replyNotice=page.locator('#dialog li').filter({hasText:'Le support vous a répondu'}).first();
  await replyNotice.locator('[data-action="notice-open"]').click();
  assert((await page.locator('#dialog').innerText()).includes('Réponse technique de contrôle 2026'),'Notification non reliée à la vraie réponse du ticket');await close();
  report.checks.push('Mise à jour et réponse support synchronisées ; diagnostics expirés/révoqués fermés');

  await reset();await role('admin');await action('alert').click();await page.locator('[name=qualification]').selectOption('Incident confirmé');await page.locator('[name=reason]').fill('Éléments techniques examinés');await submit();
  await action('incident-open').click();await action('incident-action').click();await page.locator('[name=action]').fill('Source rétablie et contrôle technique effectué');await submit();
  await action('incident-close').click();await page.locator('[name=verification]').fill('Réception des événements confirmée dans le scénario');await page.locator('[name=checked]').check();await submit();
  assert((await text()).includes('Clos · retour vérifié'),'Clôture d’incident sans état final');
  assert((await text()).includes('Source rétablie et contrôle technique effectué'),'Chronologie non conservée');
  report.checks.push('Incident : qualification, action, preuve du retour et clôture');

  await reset();await role('admin');await nav('certificates');
  const firstCertificate=await page.locator('#content tbody tr').first().innerText();
  await action('cert-renew').click();await page.locator('[name=reason]').fill('Échéance et appareil vérifiés dans le scénario');await submit();
  const renewed=await page.locator('#content tbody tr').first().innerText();
  assert(renewed!==firstCertificate&&renewed.includes('Renouvelé'),'Renouvellement sans modification du certificat');
  await nav('accounts');
  const adminRow=page.locator('#content tbody tr').filter({hasText:'ADMIN-001'});
  assert(await adminRow.locator('[data-action="account-role"]').count()===0,'Auto-attribution du rôle admin possible');
  await page.locator('[data-action="account-sessions"][data-account="CARE-002"]').click();
  await page.locator('[data-action="session-revoke"]').first().click();
  if(await page.locator('#dialog-submit').isVisible()){await page.locator('[name=reason]').fill('Session ciblée contrôlée');await submit();}
  if(await page.locator('#dialog').isVisible())await close();
  await role('user');assert(!(await text()).includes('Session non disponible'),'Révocation soignant coupe le mauvais compte');
  report.checks.push('Certificat renouvelé, rôle administrateur protégé et révocation ciblée');

  await reset();await role('admin');await nav('accounts');await action('account-create').click();
  await page.locator('[name=id]').fill('DEMO-QA-001');await submit();
  for(const expected of ['Suspendu','Actif']){
   const row=page.locator('#content tbody tr').filter({hasText:'DEMO-QA-001'});
   await row.locator('[data-action="account-toggle"]').click();await page.locator('[name=reason]').fill('Vérification du compte neuf sans session');await submit();
   assert((await row.innerText()).includes(expected),'Suspension/réactivation du compte neuf échouée');
  }
  report.checks.push('Création, suspension et réactivation d’un compte sans session');

  await reset();await nav('settings');await action('delete-request').click();await page.locator('#dialog input[type=checkbox]').check();await submit();
  await role('admin');await nav('deletions');await action('deletion-review').click();
  for(const checkbox of await page.locator('#dialog input[type=checkbox]').all())await checkbox.check();
  await page.locator('[name=proof]').fill('DEMO-PREUVE-004 : résultat du scénario');await submit();
  assert((await text()).includes('Exécutée'),'Demande non exécutée côté administration');
  await role('user');await nav('settings');await action('delete-request').click();
  assert((await page.locator('#dialog').innerText()).includes('DEMO-PREUVE-004'),'Preuve absente du suivi utilisateur');await close();
  report.checks.push('Suppression : demande utilisateur, traitement administratif et preuve partagée');
  assert(report.errors.length===0,JSON.stringify(report.errors));
 }finally{await browser.close();}
})().catch(e=>{report.failure=e.message;console.error(e.stack);process.exitCode=1;}).finally(()=>{
 fs.writeFileSync(path.join(__dirname,'captures','verification-coherence.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
});
