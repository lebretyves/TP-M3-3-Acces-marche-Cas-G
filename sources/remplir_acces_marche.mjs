import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const root=new URL('../',import.meta.url);
const data=JSON.parse(await fs.readFile(new URL('sources/finalite.json',root),'utf8'));
const w=await SpreadsheetFile.importXlsx(await FileBlob.load(fileURLToPath(new URL('supports/TP_M3_3_Acces_marche_original.xlsx',root))));
const q=w.worksheets.getItem('Qui paie');
const put=(s,a,v)=>s.getRange(a).values=[[v]];
q.getRange('C4').dataValidation={rule:{type:'list',values:['A','A en EHPAD','B','C','D','E','F','G']}};
put(q,'C4','G');put(q,'C5','Souris ergonomique 1 500 mAh : pouls/PPG, GSR, température cutanée et mouvement, application sur PC.');
put(q,'C6',data.finalite);put(q,'C7','Dispositif médical');
for(const [row,who,why] of [
 [11,'Adulte utilisant régulièrement un ordinateur','Usage personnel quotidien, comparable au positionnement d’une montre connectée. Deux fonctions : suivi des indicateurs et tendances, ET estimation du risque cardiovasculaire personnalisé.'],
 [12,'L’utilisateur qui choisit sa souris','Il décide de l’achat selon l’utilité perçue, le confort, la simplicité et le prix. Le médecin intervient pour l’interprétation médicale, pas pour l’achat.'],
 [13,'L’utilisateur, sur son budget personnel','Hypothèse B2C retenue pour le TP : achat individuel, sans remboursement attendu au départ.'],
 [14,'Oui','Dans l’hypothèse B2C, la même personne utilise, choisit et paie. Présenter le bénéfice quotidien, les limites, le prix et la maîtrise des données.']]){put(q,`C${row}`,who);put(q,`E${row}`,why);}
const base='Conception, choix des capteurs, firmware, tests logiciels et autonomie théorique ; aucune validation clinique ou matérielle de l’ensemble.';
q.getRange('C18:H22').values=[
 ['Utilisateur, sur son budget personnel','Oui','Utilité au quotidien, fiabilité, confort, simplicité, confidentialité, prix et conformité médicale',base,'Différenciation face aux montres ; utilité et prix acceptable à tester',3],
 ['Entreprise ou service de prévention et de santé au travail','Peut-être','Acceptabilité, utilité collective, mesures fiables, confidentialité et coût',base,'Voie secondaire : achat collectif à étudier, sans accès automatique de l’employeur aux données',1],
 ['Mutuelle pour ses adhérents','Peut-être','Usage durable, bénéfice sanitaire et évaluation économique',base,'Pas de bénéfice ni d’économies démontrés',2],
 ['Assurance maladie si activité admissible inscrite','Non','Indication et organisation de télésurveillance, conformité et preuves pertinentes',base,'Pas de parcours admissible établi ; suivi du stress ≠ ligne cardiaque automatiquement applicable',1],
 ['Assurance maladie si critères PECAN satisfaits','Peut-être','DM numérique thérapeutique ou de télésurveillance admissible, CE, innovation et premières preuves',base,'Éligibilité non établie ; un outil d’évaluation seul ne suffit pas',1]
];
put(q,'C27','B2C (patient)');
put(q,'C28','Hypothèse retenue : une souris de suivi personnel achetée directement par l’utilisateur, comme une montre connectée. Son intérêt est l’usage au poste informatique. La finalité médicale conserve ses exigences de conformité et de preuves.');
put(q,'C29','Pas d’effet direct sur l’achat B2C sans remboursement : l’utilisateur paie le prix de vente. Si prise en charge concernée à terme : participation de l’assuré portée à 50–60 % au 1er janvier 2027, hors exonérations applicables. Sources dans Lisez-moi.');
put(q,'C30','Valider les mesures et tendances, puis la calibration et l’utilité du score cardiovasculaire personnalisé. Tester la compréhension, le confort et le prix acceptable.');
for(const row of [5,6,11,12,13,14,28,29,30])q.getRange(`B${row}:H${row}`).format.rowHeight=row===6?65:55;
q.getRange('C18:G22').format.wrapText=true;q.getRange('B18:H22').format.rowHeight=125;

const f=w.worksheets.getItem('Frise');
f.getRange('I6:J11').values=[[1,6],[1,6],[7,24],[7,30],[31,39],[40,48]];
f.getRange('M6:M11').values=[['Oui'],['Non'],['Non'],['Oui'],['Oui'],['Oui']];
put(f,'A2','CAS PÉDAGOGIQUE B : calendrier hypothétique de télésurveillance cardiaque. Durées choisies pour le TP ; aucune prévision validée pour la souris. Orange : chemin critique.');
const answers=[
 'Q5. Parcours : 48 mois. Somme des durées : 72 mois. Gain par travail parallèle : 24 mois. Les coûts restent qualitatifs, sans montant inventé.',
 'Q6. Chemin critique : 1 → 4 → 5 → 6. Développement (3) : 6 mois de marge. Stratégie (2) : 24 mois de marge dans ce modèle de dépendances, mais à commencer dès le début en pratique.',
 'Q7. Définir tôt stratégie réglementaire et protocole clinique ; mener développement et preuves en parallèle quand faisable. Préparer en amont les dossiers et échanges avec les évaluateurs.',
 'Q8. Réglementation tardive : jalons 2/3, fixer la destination tôt. Pas de preuves : jalon 4, préparer le protocole dès la conception. Payeur absent : jalon 6, interroger les acheteurs dès le début.',
 'Q9. Souris : vente B2C retenue, donc étape 6 centrée sur prix, distribution et achat individuel. Pas de dossier de remboursement pour cette voie. La finalité médicale maintient les exigences de conformité et de preuves. Les 48 mois concernent le cas pédagogique B.'
];
answers.forEach((v,i)=>{put(f,`B${21+i}`,v);f.getRange(`B${21+i}:M${21+i}`).format={wrapText:true,rowHeight:58};});

const p=w.worksheets.getItem('Votre projet');
p.getRange('C6').dataValidation={rule:{type:'list',values:['A','A en EHPAD','B','C','D','E','F','G']}};
p.getRange('C10').dataValidation={rule:{type:'list',values:['I','IIa','IIb','III','—','À déterminer']}};
const vals={5:'Équipe 02',6:'G',7:'Souris de suivi personnel : indicateurs, tendances ET estimation du risque cardiovasculaire personnalisé.',8:data.finalite,9:'Dispositif médical',10:data.classe,11:'Règle 11 (logiciel)',12:'Oui',13:'Oui',14:'Oui',15:'Oui',16:'Oui',17:'Non',18:'Pas de modèle d’IA d’évaluation cardiovasculaire dans R3 ; architecture future non arrêtée.',21:'Non',22:'B2C (patient)',23:'L’utilisateur, sur son budget personnel.',24:'R4/R5/R8 : fausse assurance et retard de prise en charge cardiovasculaire.',25:'R2/R3 : échauffement de la batterie ou de l’alimentation, brûlure.',26:'R9 : divulgation de données physiologiques ou médicales.',27:'Avant le 30 octobre : définir le score (événement, horizon, données), le protocole de validation et les décisions permises ; préparer des entretiens sur utilité, confort et prix.'};
for(const [r,v] of Object.entries(vals))put(p,`C${r}`,v);
put(p,'C17','Pas encore décidé');
const just={5:'Projet pédagogique ; aucune donnée personnelle dans le dépôt.',6:'Objectif confirmé dans le TP4 puis réaffirmé le 19 octobre 2026.',7:'Analogie d’usage et de commercialisation avec une montre, sans équivalence de capteurs, performances ou certification.',8:'Les deux fonctions sont retenues comme hypothèse produit. Le suivi technique existe dans R3 ; le score personnalisé reste à développer et valider.',9:'La prévention d’une maladie motive la qualification ; les capteurs seuls ne suffisent pas.',10:'IIa : hypothèse du TP, règle 11, score informant la prévention. Réexaminer IIb/III selon le rôle des résultats et les conséquences des erreurs. Aucune certification acquise.',12:'Système qualité à établir pour le développement médical ; aucune certification acquise.',13:'Gestion des risques ; cotations préparatoires du M3-2 actualisées.',14:'Cycle de vie du logiciel médical, tests, maintenance et traçabilité à organiser.',15:'Compréhension des résultats, erreurs d’usage et confort à évaluer.',16:'Cybersécurité du cycle de vie : accès, intégrité, identité et mises à jour à valider.',18:'Un traitement numérique ou une règle de seuil ne prouve pas l’existence d’une IA clinique.',20:'Base juridique, condition de l’article 9, droits, accès et conservation à documenter ; AIPD préparatoire disponible.',23:'Choix du TP : vente B2C, comme une montre connectée. Aucun remboursement nécessaire à ce modèle.',24:'Gravité conservatrice G3 ; pas de fréquence mesurée. Validation clinique et compréhension des limites nécessaires.',25:'Pack protégé, détrompage, essais thermiques et électriques nécessaires.',26:'Limiter les accès et protéger les fichiers ; partage au médecin choisi par l’utilisateur.',27:'Q10 : spécifier le calcul du score et la preuve clinique manquante, puis vérifier l’intérêt du positionnement B2C.'};
for(const [r,v] of Object.entries(just))put(p,`D${r}`,v);
put(p,'D5','Équipe 02, cas G ; prototype pédagogique.');
// The future risk model is not specified; distinguish that choice from the current R3 code.
const originalAiGuidance=p.getRange('D17').formulas[0][0];
p.getRange('D17').formulas=[['=IF(C17="Pas encore décidé","Choix de l’IA non arrêté pour le futur score ; pas de modèle d’IA cardiovasculaire dans R3",'+originalAiGuidance.slice(1)+')']];
// Preserve automatic guidance, explicitly handling the unresolved classification.
p.getRange('D11').formulas=[['=IF(C10="À déterminer","Classe et procédure à confirmer ; organisme notifié si IIa/IIb/III",IF(OR(C10="IIa",C10="IIb",C10="III"),"Organisme notifié requis",IF(C10="I","Procédure classe I à vérifier","Vérifier la qualification")))']];
p.getRange('C29').formulas=[['=IF(COUNTBLANK(C5:C27)>0,"Réponses manquantes : "&COUNTBLANK(C5:C27),IF(C10="À déterminer","Fiche renseignée ; classe réglementaire à déterminer","Fiche renseignée ; classe proposée pour le TP, non certifiée"))']];
p.getRange('C5:D27').format.wrapText=true;
p.getRange('A8:D8').format.rowHeight=94;
for(const r of [7,10,17,18,23,24,25,26,27])p.getRange(`A${r}:D${r}`).format.rowHeight=65;
p.getRange('A29:D29').format.rowHeight=32;

const read=w.worksheets.getItem('Lisez-moi');
const notes=[
 'Choix confirmé le 19 octobre 2026 — Équipe 02, cas G : hypothèse 2, dispositif médical. Deux fonctions prévues : suivi physiologique et estimation personnalisée du risque cardiovasculaire. Performances à valider ; durées de la frise pédagogiques.',
 'Q1. Hypothèse grand public : l’utilisateur profite, choisit et paie la souris. Mettre en avant l’usage quotidien, le confort, la fiabilité, le prix et la maîtrise des données. Le médecin peut recevoir des informations si l’utilisateur le souhaite.',
 'Q2 — Hypothèse 1 non retenue : observer ses habitudes et organiser des pauses, sans évaluer un risque de maladie. Hors DM si les fonctions et communications restent non médicales : pas de CE médical, autres obligations du produit connecté à examiner. Rappels non implémentés dans R3.',
 'Q2 — Version médicale retenue : '+data.finalite+' IIa est retenue comme hypothèse pour un score informatif de prévention. La classe dépend des conséquences des décisions ; aucune certification acquise.',
 'Q3/Q4. B2C prioritaire (note 3), mutuelle secondaire (note 2), achat collectif exploratoire (note 1). LATM non établi, PECAN seulement si admissible. Les preuves manquantes concernent la finalité médicale, l’usage quotidien et le prix acceptable.',
 'Analogie retenue : comme une Apple Watch, objet acheté par son utilisateur pour le suivi personnel. Certaines fonctions de la montre ont une destination médicale propre. La souris prévoit tendances ET score personnalisé, sans ECG. L’analogie ne prouve ni ses performances ni sa classe.',
 'Étude souris et stress : https://pmc.ncbi.nlm.nih.gov/articles/PMC9855736/',
 'Fitbit, combinaison EDA/pouls/température : https://blog.google/products-and-platforms/devices/fitbit/how-we-trained-fitbits-body-response-feature-to-detect-stress/',
 'Apple, fonction ECG et limites : https://support.apple.com/fr-fr/120278',
 'Stress et santé cardiovasculaire : https://www.heart.org/en/healthy-living/healthy-lifestyle/stress-management/stress-and-heart-health',
 'MDR, article 2 et annexe VIII, règle 11 : https://eur-lex.europa.eu/eli/reg/2017/745/oj/fra',
 'HAS, voies de remboursement et PECAN : https://www.has-sante.fr/jcms/c_928541/fr/comprendre-l-evaluation-des-dispositifs-medicaux',
 'Décret 2026-810, taux : https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000054733597 ; entrée en vigueur : https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000054733599',
 'ANS, champ HDS : https://esante.gouv.fr/faq/quel-est-le-champ-dapplication-de-la-legislation-relative-lhebergement-de-donnees-de-sante-caractere-personnel',
 'CNIL, données médicales et employeur : https://www.cnil.fr/fr/cnil-direct/question/donnees-sur-la-sante-un-employeur-peut-il-les-connaitre',
 'Comparatifs et références consultés le 19 octobre 2026. Sources projet : finalite.json, classification M3-1 et risques M3-2 réalignés. Aucun prix de vente, client ou remboursement acquis n’est inventé.'
];
notes.forEach((v,i)=>{put(read,`B${22+i}`,v);read.getRange(`B${22+i}`).format={wrapText:true,rowHeight:55};});
w.recalculate();
const actual=f.getRange('C13:C18').values.map(r=>r[0]);
if(actual[0]!==48||actual[2]!==72||actual[3]!==24||actual[4]!==4||actual[5]!=='6 sur 6')throw Error(JSON.stringify(actual));
if(q.getRange('C31').values[0][0]!=='OK')throw Error('Voie incohérente');
if(q.getRange('C23').values[0][0]!==q.getRange('B18').values[0][0]||p.getRange('C22').values[0][0]!=='B2C (patient)')throw Error('Le classement doit placer B2C en tête et le reprendre dans la fiche');
// Verify that the route ranking responds to its inputs, then restore.
put(q,'H18',1);w.recalculate();if(q.getRange('C23').values[0][0]!==q.getRange('B20').values[0][0])throw Error('Classement des voies figé');put(q,'H18',3);w.recalculate();
for(let i=0;i<5;i++)for(const row of w.worksheets.getItemAt(i).getUsedRange().values)for(const v of row)if(typeof v==='string'&&/^#(REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|CALC!)/.test(v))throw Error(v);
// Verify that the timing checks respond to a violation, then restore.
put(f,'I10',30);w.recalculate();if(f.getRange('L10').values[0][0]==='OK')throw Error('Dépendance non contrôlée');put(f,'I10',31);
w.recalculate();
await fs.mkdir(new URL('tmp/m3_acces/',root),{recursive:true});
for(const [sheetName,range,id] of [['Qui paie','B4:H14','roles'],['Qui paie','B17:H24','voies'],['Qui paie','B26:H31','choix'],['Frise','A5:M18','frise'],['Frise','N5:BU11','barres'],['Frise','B21:M25','reponses'],['Votre projet','A4:D16','fiche_1'],['Votre projet','A17:D29','fiche_2'],['Lisez-moi','B22:B27','contexte'],['Lisez-moi','B28:B37','sources']]){
 const img=await w.render({sheetName,range,scale:1,format:'png'});
 await fs.writeFile(new URL(`tmp/m3_acces/${id}.png`,root),new Uint8Array(await img.arrayBuffer()));
}
const out=await SpreadsheetFile.exportXlsx(w);await out.save(fileURLToPath(new URL('analyses/m3/acces_marche_eq02.xlsx',root)));
console.log(JSON.stringify({duree:48,sequentiel:72,gain:24,controles:actual[5],fiche:p.getRange('C29').values[0][0]}));
