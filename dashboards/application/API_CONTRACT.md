# SKELIVIA — contrat domaine persistant

## Événements d’usage du simulateur

L’enveloppe MQTT `skelivia.telemetry.v1` accepte le champ facultatif `events` (liste vide par défaut, au plus quatre éléments). Chaque élément contient uniquement `kind` (`pause_reminder`, `high_force`, `quiet_contact` ou `absent`), `at_seconds` (décalage fini entre zéro et la durée de la fenêtre transmise) et `origin` (`computed` ou `manual`). Un type ne peut figurer qu’une fois dans une fenêtre. Les événements avec qualité `invalid` ou `calibration_required` sont refusés ; aucun destinataire ni titre arbitraire n’est accepté.

Le worker crée les notifications pour le propriétaire actif de la souris authentifiée, dans la même transaction que la mesure et le reçu anti-rejeu. Les titres portent « Simulation » et les données `synthetic:true`. Une temporisation de 60 secondes par souris et type empêche les répétitions, y compris entre deux sessions du simulateur. Les résultats de traitement sont conservés dans les métadonnées chiffrées de la mesure (`usage_events`) : `notification_created`, `cooldown`, `pause_disabled`, `pause_snoozed` ou `owner_unavailable`. Ils ne sont pas ajoutés aux catégories de mesures partagées avec le soignant.

Le rappel de pause exige `pause_enabled:true` et l’absence de report actif. Il réutilise le canal `pause` de l’adaptateur de notifications, qui contrôle à nouveau canaux, horaires silencieux, désactivation, abonnement et configuration avant tout envoi. Les trois autres types utilisent `kind:usage` et restent dans le dashboard utilisateur. Ce sont des événements de démonstration, sans diagnostic ni seuil médical validé. La migration RLS ajoute uniquement la lecture des enregistrements `settings` au worker pour respecter les préférences ; elle n’accorde aucun accès aux documents ou aux mesures en lecture.

`GET /api/simulation-notifications?run_id=UUID` exige la session d’un utilisateur actif. Il consulte uniquement ses 500 notifications les plus récentes des dernières 24 heures, puis filtre les événements synthétiques liés à cette exécution. Réponse : `{run_id,notifications:[{id,title,event_kind,origin,created_at,sequence}],checked_at,truncated,scope:"own_notifications"}`. Les dates sont ISO UTC. `truncated:true` signifie qu’une notification plus ancienne peut avoir été omise : une liste vide ne prouve alors pas une absence. Aucun choix de destinataire, contenu de dossier, mesure, secret ni jeton n’est exposé. Cet endpoint ne marque pas les notifications comme lues et ne prouve pas une réception sur téléphone ou montre. Les anciennes notifications sans lien `simulation_run/sequence` ne sont pas rattachées rétroactivement.

`GET /api/workspace` exige une session authentifiée. Aucun sélecteur de rôle : `role` vient du compte serveur (`user`, `clinician`, `employer`, `support`, `security`). `POST /api/actions` reçoit `{ "action": "nom", "payload": {...} }`, JSON strict et jeton CSRF existant. Réponse `{ok:true,id?:string}` puis recharger workspace. Erreurs 404 périmètre, 409 transition/prérequis, 422 validation, 403 réauthentification. Aucune commande ne prouve une intervention physique.

## État

Commun : `role`, `account:{id,name,role}`, `settings`, `notifications[]`, `capabilities`, `server_time`, `synthetic` (vrai seulement si toutes les mesures/documents exposés sont explicitement fictifs ; les opérations persistantes ne sont pas étiquetées fictives par défaut).
Chaque objet métier a `id`, `status`, `created_at`, et ses champs métier au premier niveau. Dates ISO UTC ; expirations secondes Unix.

- user : `patient_id`, `measures[]` (id,patient_id,recorded_at,quality,metrics,calibration,synthetic), `documents[]` (patient_id,kind advice/report,title,body,version,document_id,author_id), `shares[]` (clinician_id,start,end,categories,expires,active), `clinicians[]` (id,name), `devices[]`, `tickets[]`, `jobs[]`, `deletions[]`, `sessions[]`.
- clinician : `patients[]` (id,name,access,shares[]), `measures[]` filtrées dates/catégories, `documents[]` versions autorisées, `reminders[]`, `recommendations[]`, `organisations[]` (id), `tickets[]`, `sessions[]`, `measurement_updates[]` (id,title,version,comparability). Aucun export de mesures soignant.
- employer : `recommendations[]` (title,body,category,status,history[]). Aucune mesure, aucun document patient, aucun identifiant patient. Pas de sessions affichées.
- support : `tickets[]` attribués seulement dans un SupportScope actif, `devices[]` des diagnostics actifs (état technique uniquement), `jobs[]`, `sessions[]`, `approved_patches[]` (id,title,version). Ticket : owner_id,device_id nullable,title,category,messages[{author_id,body,at}],diagnostic_expires,diagnostic_active,checks. Informations diagnostics masquées après expiration. Les tickets logiciels soignant n'ont aucune souris patient associée.
- security : `accounts[]` (id,name,role,org_id,active), `account_requests[]`, `incidents[]`, `patches[]`, `certificates[]`, `components[]`, `proofs[]`, `audit[]`, `deletions[]`, `jobs[]`, `sessions[]` ciblables par compte. Sessions : id public dérivé,account_id,expires,last_seen,current ; jamais token,hash ni CSRF. Jamais mesures/documents/tickets médicaux.

`devices` : id,owner_id,connection,last_seen,freshness_seconds,quality,usable,firmware,calibration,calibration_status,history[]. Sans horodatage valide : unknown ; dernier paquet vieux de plus de 120 secondes : stale, sans prétendre connaître la connexion TLS. Les états retired/lost/revoked sont conservés. `usable` exige fraîcheur, qualité valid et calibration reconnue. Résultats matériels uniquement via adaptateur vérifié. `jobs`: id,kind,target_id,status,created_at,result (résultat technique limité), jamais secrets. `notifications`: id,kind,title,route,read,created_at ; aucun contenu médical.

Mesures : `window_start`, `window_end`, `window_duration_seconds` au premier niveau, null pour les anciens points sans fenêtre. Les pressions sont pondérées par durée seulement si les fenêtres sont connues ; les anciens points ne deviennent pas des intervalles inventés. Workspace fournit `measure_window:{start,end}`, `measure_limit`, `measures_has_more`, `measures_next_cursor`. La fenêtre par défaut couvre 30 jours UTC, limitée à 1000 points initiaux.

`GET /api/measures?start=YYYY-MM-DD&end=YYYY-MM-DD&limit=1000&cursor=...&patient_id=...` : user ou clinician autorisé seulement ; patient_id facultatif et contrôlé. Période 1 à 90 jours inclus, limit 1 à 1000. Réponse `{measures,window:{start,end},limit,has_more,next_cursor}`. Ordre recorded_at décroissant puis id décroissant ; curseur signé lié au compte, au patient et à la fenêtre. Dates et droits sont appliqués avant la limite SQL. Repartir de la première page après changement de fenêtre ou révocation ; ne pas annoncer une synthèse exhaustive si has_more.

## Actions et payloads exacts

Champs marqués `?` facultatifs. Tous les autres obligatoires. Identifiants max80, titres max160, textes max2000. Noms d'action stables.

|Action|Payload|Rôle|
|---|---|---|
|settings.save|large_text:bool?,high_contrast:bool?,pause_enabled:bool?,pause_minutes:int?,channels:{pause/advice/report/support/calibration:"none/phone/watch/both"}?,quiet_start:"HH:MM"?,quiet_end:"HH:MM"?|tous (notifications user seulement)|
|notification.read|id|propriétaire|
|pause.snooze|minutes:1..120|user|
|share.create|clinician_id,start:"YYYY-MM-DD",end,categories:[contact,pressure,moves],duration_hours:1..2160|user avec relation|
|share.revoke|id|user propriétaire|
|document.publish|patient_id,kind:"advice/report",title,body,document_id?:id|clinician lié + partage actif ; nouvelle version si document_id|
|reminder.create|patient_id,due:"YYYY-MM-DD",body|clinician lié|
|reminder.delete|id|auteur|
|recommendation.publish|org_id,title,body,category:"equipment/layout/organisation"|clinician lié à un patient de cette organisation|
|recommendation.revise|id,title,body,category:"equipment/layout/organisation"|clinician auteur ; ancienne version conservée dans history|
|recommendation.status|id,status:"todo/in_progress/done/blocked"|employer organisation|
|ticket.create|title,body,category:"connection/calibration/replacement/loss/software",device_id?:id|user/clinician ; appareil personnel seulement|
|ticket.reply|id,body|propriétaire ou support attribué|
|ticket.status|id,status:"in_progress/waiting/resolved"|support attribué ; clôture exige contrôles et résultat matériel vérifié|
|ticket.checks|id,connection:bool,sensors:bool,calibration:bool|support attribué + diagnostic actif|
|diagnostic.revoke|id (ticket)|support attribué ou security|
|diagnostic.request|id (ticket),duration_minutes:1..60,reason|support attribué ; demande approbation propriétaire|
|diagnostic.approve|id (job)|propriétaire ticket ; fenêtre bornée|
|device.calibrate|device_id,ticket_id?:id|user propriétaire ou support attribué + diagnostic actif ; job pending|
|device.replace|ticket_id,new_device_id|support attribué + diagnostic actif ; job pending|
|device.update|ticket_id,patch_id|support attribué + diagnostic actif + correctif approuvé ; job pending|
|security.report|body,ticket_id?:id|user/clinician/support ; incident technique minimal|
|incident.qualify|id,status:"confirmed/false_positive",reason|security|
|incident.action|id,body|security|
|incident.close|id,proof|security ; action préalable exigée|
|account.request|target_id?:id,operation:"create/suspend/reactivate/role",role?:"user/clinician/employer/support/security",name?:string,username?:string,org_id?:string,reason|security ; crée demande, pas privilège immédiat|
|account.approve|id|security distinct du demandeur et de la cible ; réauth récente|
|session.revoke|id,reason|propriétaire ou security ; ciblage serveur, réauth pour tiers|
|certificate.request|device_id,operation:"renew/revoke",reason|security ; job pending|
|patch.evaluate|id,priority:"low/medium/high/critical",exposure,tests,decision:"review/approved/deferred",reason|security ; pas d'auto-approbation|
|deletion.request|reason|user ; état demandé|
|deletion.review|id,reason|security ; job de contrôle/exécution, aucune fausse preuve|
|access.check|{}|security ; preuve du contrôle DB seulement|

GET `/api/export?kind=personal&start=YYYY-MM-DD&end=YYYY-MM-DD` user seulement (période personnelle maximale 90 jours), ou `kind=prevention` employer seulement. JSON téléchargeable avec unités/calibration/lacunes ; aucun export soignant. L'export personnel est complet ou refusé 413 au-delà de 10 000 mesures, jamais tronqué silencieusement. L'adaptateur FHIR dispose de son propre plafond explicite de 1000.

Les opérations d'infrastructure restent `pending/blocked/sent` tant qu'un adaptateur n'a pas exécuté et vérifié le résultat. Les commandes matérielles sont en attente d'ACK identifié ; un second clic ne crée pas une commande doublon lorsqu'une commande est sent. Le provisionnement hors ligne peut produire `provisioned_inactive`, jamais une session ni un mot de passe connu. Voir les procédures opérateur ci-dessous.

## Couverture des 71 décisions retenues

Cette table décrit le domaine applicatif, pas une certification de fonctionnement matériel ni de mise en production. Les 16 décisions refusées ne possèdent aucune action. La lecture/frontend complète ce contrat avec filtres, graphiques et comparaison des mesures déjà autorisées.

|Décisions|API / données persistantes|Condition ou limite effective|
|---|---|---|
|U04,U10|documents advice/report et versions|Contenu uniquement rédigé par soignant, aucun diagnostic automatique|
|U12,U13|device.calibrate, devices, jobs|Commande pending ; résultat exige adaptateur matériel, pas un clic utilisateur|
|U14,U15|measures datées, unités/calibration/lacunes|Le frontend peut regrouper par période sans inférer santé ni temps assis|
|U16|settings.save,pause.snooze|Préférences stockées ; envoi externe non configuré|
|U17|share.create/revoke, DomainGrant|Relation actuelle + dates + catégories + expiration serveur|
|U18|ticket.create/reply, tickets|Propriétaire ou support attribué avec périmètre actif|
|U19|GET export personal|Période personnelle ; aucun export soignant|
|U20,U21|sessions,session.revoke,security.report|Détection de nouvelle connexion dépend de l'authentification main.py ; tableau de bord uniquement|
|UA01,UA03,UA04,UA05,UA06|settings.channels,notifications/jobs,api/push|Adaptateur Web Push présent, désactivé sans configuration de déploiement ; aucun envoi réel effectué pendant les tests. Montre via relais OS seulement|
|UA07,UA08|settings.channels,quiet_start/end|Adaptateur vérifie canaux, période calme, compte et abonnement avant chaque tentative ; accepted_by_provider ne prouve pas réception|
|UA09|large_text/high_contrast|Préférences propres au compte|
|UA11,UA12|ticket.create loss/replacement,device.replace/update,jobs|Perte/remplacement et mises à jour demandés ; état matériel vérifié via ACK seulement|
|UA13|deletion.request/review,jobs,operator CLI|Suppression applicative exécutable après examen et levée explicite des contraintes de conservation ; preuve et tombstone conservés|
|S01,S02,S03|patients,measures filtrées|Relation active et partage actif ; comparaison uniquement dans dates/catégories autorisées|
|S04,S05,S06|document.publish|Versions patient immuables, auteur et date ; unicité DB document/version|
|S07,S08|recommendation.publish/revise/status|Organisation liée, aucun champ patient ; statuts sans motif de blocage|
|S09|reminder.create/delete|Rappel personnel ; ne prolonge aucun accès aux données|
|S12,S13|measures.calibration,measurement_updates|Comparabilité explicite ou inconnue ; aucun résultat matériel inventé|
|S14,S15,S16,S17|sessions,security.report,tickets,settings|Sessions propres ; ticket logiciel sans souris patient ; accessibilité persistée|
|E01,E02,E05|recommendations,status|Organisation strictement filtrée ; comptage par statut côté frontend|
|E06,E07|notifications,history et versions recommandation|Publication/correction notifiées sans données médicales|
|E08,E09|export prevention,settings|Pas de mesures individuelles ni sessions employeur exposées|
|T01,T02|tickets assignés,reply/status,SupportScope|Droit retiré dès désactivation du périmètre|
|T03,T04|device.calibrate,diagnostic.request/approve/revoke|Accord propriétaire et fenêtre max60min ; aucun diagnostic technique après expiration|
|T05,T06|device.replace/update|Job persistant, correctif approuvé, diagnostic actif ; ACK matériel indispensable|
|T07,T08|devices.history,ticket.checks/status|Historique renseigné par adaptateur ; clôture matérielle refuse simple auto-attestation sans calibration vérifiée|
|T09,T10,T11,T12|security.report,notifications,sessions,settings|Messages techniques minimaux, pas de santé|
|A01|account.request/approve,operator CLI|Approbateur distinct du demandeur et de la cible ; réauth<5min ; adaptateur crée identité IdP et compte désactivés, enrôlement MFA distinct requis|
|A02,A03|patch.evaluate,patches,jobs|Évaluateur et approbateur distincts ; état déployé dépend de preuve externe|
|A04,A05,A10|incident.qualify/action/close,session.revoke,account.request|Événement confirmé, action préalable et preuve de vérification ; suspension après approbation distincte|
|A06|certificate.request|Opération pending jusqu'à adaptateur PKI ; aucune clé privée dans API|
|A07,A08,A09|proofs,audit,incidents|Sauvegardes et silence des sources exigent preuves/événements des services ; domaine ne les invente pas|
|A11,A12|deletion.review,access.check,DomainDiagnostic|Tombstone conserve patient_id ; contrôle DB des accès, distinct d'un contrôle broker/pare-feu|
|A13,A14|components,settings|Inventaire initial explicite, fin de support inconnue signalée ; préférences persistantes|

Les fixtures `seed_domain` sont explicites, isolées et idempotentes ; elles n'accordent aucun partage par défaut ni diagnostic matériel actif. Les résultats des capteurs réels ne doivent jamais être marqués fictifs. Le réensemencement respecte les tombstones de suppression. Les adaptateurs présents ne remplacent pas la qualification du matériel, l'enrôlement IAM, les règles de conservation ou les prérequis de déploiement mobile.

## Opérations privilégiées hors API

Les deux CLI utilisent uniquement `SKELIVIA_OPERATOR_DATABASE_URL_FILE` et exigent PostgreSQL avec l'identité `skelivia_owner`. Le service web ne reçoit pas cet accès. Sans `--execute`, mode dry-run sans mutation ni appel IdP. Ne jamais lancer ces commandes sur des données réelles sans job validé et procédure opérateur applicable.

- Suppression : `python -m scripts.domain_operations --job ID --dry-run`. Exécution explicitement autorisée : ajouter `--execute --retention-cleared --policy-reference REF` en remplaçant `--dry-run`. Vérifie demande, patient et examinateur ; supprime données applicatives et sessions, révoque partages/diagnostics/push, conserve une preuve minimale avec patient_id pour réconciliation de restauration. Résultat `completed_database` limité à la base applicative : cycle IdP, CRL broker, expiration des sauvegardes et copies déjà téléchargées restent des obligations séparées documentées dans la preuve.
- Provisionnement : `python -m scripts.account_provision --job ID --dry-run`. Exécution avec `--execute --policy-reference REF`, après approbation distincte encore valide. Exige en plus `SKELIVIA_OPERATOR_KEYCLOAK_TOKEN_FILE` (jeton opérateur court), `SKELIVIA_OPERATOR_KEYCLOAK_URL`, éventuellement `SKELIVIA_OPERATOR_KEYCLOAK_REALM` et `SKELIVIA_OPERATOR_CA_FILE`. HTTPS obligatoire sauf opt-in explicite `SKELIVIA_OPERATOR_ALLOW_PRIVATE_HTTP=true` limité à keycloak/localhost/127.0.0.1. Crée une identité désactivée marquée par le job et vérifiée, une correspondance OIDC et un compte applicatif désactivé. En cas de reprise, une identité préexistante étrangère au job est refusée. Enrôlement MFA, vérification d'identité, activation IdP puis demande/approbation de réactivation applicative sont des étapes distinctes ; aucune invitation ou livraison de secret n'est automatique.

Web Push : voir `PUSH_CONTRACT.md`. Rôle SQL séparé `skelivia_push`, payload générique sans santé, souscriptions chiffrées par propriétaire, transport mocké dans les tests, retries bornés. `SKELIVIA_PUSH_ENABLED=false` demeure le réglage de déploiement tant que domaine HTTPS accessible, contact VAPID réel et accès réseau autorisé ne sont pas configurés. Un iPhone exige l'application web ajoutée à l'écran d'accueil et un consentement explicite ; aucune montre autonome n'est promise.
