const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const url = 'http://127.0.0.1:8771';
function inspect() {
  return new Promise(resolve => {
    const request = http.get(url, response => {
      let body='';
      response.setEncoding('utf8');
      response.on('data', chunk => { if(body.length<20000) body+=chunk; });
      response.on('end', () => resolve(response.statusCode===200 && body.includes('SKELIVIA') ? 'ready' : 'occupied'));
      response.on('error', () => resolve('occupied'));
    });
    request.setTimeout(1200, () => request.destroy());
    request.on('error', error => resolve(error.code==='ECONNREFUSED' ? 'absent' : 'occupied'));
  });
}
(async () => {
  const initial=await inspect();
  if(initial==='occupied') throw new Error('Le port 8771 est utilise par un autre service ou ne repond pas. Aucun service existant n’a ete arrete.');
  if(initial==='absent') {
    const server=path.join(__dirname,'serveur-local.cjs');
    if(!fs.existsSync(server)) throw new Error('Le serveur de presentation manque dans le dossier verification.');
    const child=spawn(process.execPath,[server],{cwd:path.dirname(server),detached:true,stdio:'ignore',windowsHide:true});
    child.on('error', error => {console.error(error.message);process.exitCode=1;});
    child.unref();
    let ready=false;
    for(let attempt=0;attempt<30;attempt++) {
      await new Promise(resolve=>setTimeout(resolve,250));
      if(await inspect()==='ready'){ready=true;break;}
    }
    if(!ready) throw new Error('Le serveur local n’a pas pu demarrer. Relancez depuis le terminal pour consulter le message.');
  }
  console.log('SKELIVIA : '+url);
  if(!process.argv.includes('--no-open')) {
    const browser=spawn('cmd.exe',['/d','/c','start','',url],{detached:true,stdio:'ignore',windowsHide:true});
    browser.on('error',()=>console.log('Ouvrez cette adresse dans votre navigateur : '+url));
    browser.unref();
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
