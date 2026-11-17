# Infrastructure locale SKELIVIA

Le projet Compose `skelivia` est indépendant du P1 et du banc PostgreSQL P2 existant. Il n'utilise ni leurs volumes ni leur port 55432. Cette infrastructure contient uniquement des données synthétiques ; le contrat refuse `synthetic:false` sans option pour contourner ce refus.

## Services et accès

| Service | Réseau / rôle | Port publié sur le PC |
|---|---|---|
| proxy nginx | HTTPS, routage application et identité | `127.0.0.1:8443` uniquement |
| app FastAPI | API, session OIDC côté serveur, autorisations | aucun |
| worker Python | ingestion MQTT et commandes techniques bornées | aucun |
| push Python | notifications internes et boîte d'envoi, envois externes désactivés | aucun |
| broker Mosquitto | MQTT TLS 8883, certificat client obligatoire | aucun |
| db PostgreSQL | base métier et base identité distinctes | aucun |
| Keycloak | identité, mot de passe + OTP, PKCE | aucun |
| migrate | tâche ponctuelle propriétaire du schéma | aucun |

La connexion locale est `https://localhost:8443`. Le certificat est signé par une autorité locale propre au banc, pas par une autorité publique. Le certificat public de cette autorité est `.runtime/infra/pki/public/ca.pem`. Aucun ajout automatique au magasin de confiance système n'est effectué.

Sur le poste testé, Norton Web/Mail Shield intercepte le HTTPS de localhost et présente un certificat de remplacement signé par « Norton Web/Mail Shield Untrusted Root ». Le client Python qui exige uniquement la CA SKELIVIA refuse correctement cette chaîne. La vérification stricte du certificat original s'effectue dans le réseau Docker privé. Ce constat ne justifie ni la désactivation automatique de l'antivirus, ni un `verify=false` en production ; la confiance et l'interception HTTPS du poste doivent être traitées par l'opérateur. Une session de test navigateur configurée pour ignorer les erreurs HTTPS ne prouve pas la confiance de la chaîne sur le poste.

Le backchannel OIDC utilise `https://proxy/auth/realms/skelivia` et vérifie la CA locale ; l'émetteur des jetons reste exactement `https://localhost:8443/auth/realms/skelivia`. Les routes applicatives sont `/oidc/*`. Le proxy bloque `/auth/admin/` ; l'administration Keycloak s'effectue depuis le réseau privé via un opérateur habilité.

## Préparation et démarrage

Depuis `dashboards/application` avec l'environnement Python du projet :

```powershell
.venv/Scripts/python.exe scripts/prepare_infra.py --operator-account 'Yves\lebre'
docker compose -f infra/compose.yaml config --quiet
docker compose -f infra/compose.yaml build app
docker compose -f infra/compose.yaml up -d db broker keycloak
docker compose -f infra/compose.yaml run --rm --no-deps -T migrate
docker compose -f infra/compose.yaml up -d app worker proxy
docker compose -f infra/compose.yaml up -d push
```

L'option `--operator-account` est propre au compte Windows qui exécute Docker Desktop. Elle sert lorsque le processus de préparation tourne sous un autre compte restreint. Les droits du répertoire privé sont réservés au processus de préparation, à cet opérateur explicitement nommé, à SYSTEM et aux administrateurs. Sous Linux, le répertoire est créé en mode 0700 et les fichiers privés en 0600 ; une adaptation des UID de montage est nécessaire avant déploiement hors Docker Desktop.

La préparation est idempotente : elle ne remplace pas les clés, mots de passe ni certificats existants. Les données `.runtime/` sont exclues de Git et du contexte Docker. Ne pas supprimer les volumes pour résoudre une erreur de démarrage. Ne pas utiliser `docker system prune`, ni arrêter les autres projets.

## Contrat des secrets

Les secrets sont des fichiers sous `.runtime/infra/secrets`, montés uniquement aux services nécessaires. Aucune valeur n'est inscrite dans le YAML, les paramètres de commande ou les journaux applicatifs.

- `owner_database_url` : rôle `skelivia_owner`, utilisé uniquement pour migrations/opérations explicites.
- `app_database_url`, `worker_database_url` : comptes distincts sans privilèges superutilisateur, DDL, création de rôle ou contournement RLS.
- `push_database_url` et paire VAPID : rôle SQL distinct et clé P-256 du service de notifications. `SKELIVIA_PUSH_ENABLED=false` et aucun contact VAPID inventé ; les envois sur téléphone/montre ne sont donc pas activés par ce banc local.

Pour un futur déploiement Push activé, le validateur actuel de l'API doit également lire la paire VAPID afin de vérifier sa correspondance ; le Compose de ce banc désactivé ne monte la clé privée que dans le service Push. Préparer ce raccordement ou séparer cette validation avant activation ; un simple changement du booléen ne suffit pas.
- `data_key` : clé AES-GCM de 32 octets encodée en base64 standard, partagée seulement par les processus applicatifs qui doivent traiter les champs chiffrés.
- `backup_key` : autre clé AES-GCM, distincte de la clé des données, jamais montée dans l'application web.
- `oidc_client_secret` et `identity-map.json` : client confidentiel et rattachement explicite des sujets OIDC aux comptes locaux.
- `login_<compte>` : mots de passe aléatoires des comptes de test ; ne pas les copier dans un rapport ou un dépôt. Les utilisateurs enrôlent leur OTP via Keycloak.
- Les clés privées de CA et de signature de firmware restent dans les répertoires `pki/offline-*`, jamais montés dans l'API, le worker ou le broker.

`SKELIVIA_DATABASE_URL_FILE`, `SKELIVIA_DATA_KEY_FILE`, `SKELIVIA_OIDC_CLIENT_SECRET_FILE`, `SKELIVIA_OIDC_IDENTITY_MAP_FILE` et `SKELIVIA_CA_FILE` désignent les fichiers montés. Les autres paramètres OIDC et MQTT sont visibles dans Compose et ne contiennent aucun secret.

## Identité et authentification

Le realm impose le parcours LoA 2 : mot de passe puis OTP obligatoire. Le client utilise Authorization Code, PKCE S256, secret client, redirection exacte et aucun grant direct ni flux implicite. Le scope `basic` est nécessaire pour `auth_time` et `sid`, avec `acr`, `profile`, `email` et `web-origins`. Le niveau ACR ne provient pas d'un attribut arbitraire : il résulte du flow d'authentification. Les vérifications de jetons, nonce, état, origine, session et droits métier appartiennent à l'application.

Les rôles de l'application ne sont pas auto-attribués depuis un nom utilisateur envoyé par le navigateur. Le mapping des sujets est généré pour les huit comptes fictifs. Il ne constitue ni une identité professionnelle vérifiée ni un raccordement Pro Santé Connect.

Les journaux d'accès nginx et Uvicorn sont désactivés pour éviter d'enregistrer les paramètres de callback OIDC. Les erreurs techniques du worker sont des codes bornés, sans mesures ni payload brut.

## Contrat MQTT et ingestion

Le broker exige TLS avec validation du serveur et certificat client. `use_identity_as_username` associe le CN du certificat à l'identité ACL. Les CN `skm-001` et `skm-002` sont opaques, sans nom ni identifiant patient. Chaque appareil peut publier seulement ses propres topics `telemetry` et `ack`, et lire seulement son topic `commands`. Le worker peut lire la télémétrie et les ACK, puis écrire les commandes ; il ne peut pas publier une télémétrie à la place d'un appareil.

Un paquet de télémétrie V1 contient : `schema_version=skelivia.telemetry.v1`, `synthetic=true`, `device_id`, `session_id` UUID canonique, `sequence`, `window_start` et `measured_at` UTC, versions firmware/algorithme/calibration, `quality` et `metrics`. Il décrit **un intervalle d'agrégats**, pas un compteur cumulatif depuis le démarrage ; ce n'est pas le payload P1 directement réutilisé. L'intervalle commence strictement avant `measured_at`, dure au plus 3600 secondes et ne chevauche aucun intervalle déjà accepté pour cet appareil, même après changement de session. `contact_seconds` ne peut dépasser la durée de l'intervalle. Les métriques acceptées sont `contact_seconds`, `episodes`, `thumb_pct`, `palm_pct` avec bornes numériques strictes. Les champs supplémentaires, doublons JSON, NaN, identités divergentes et paquets retained sont refusés.

Le worker vérifie le registre de certificats, le rattachement serveur de l'appareil, la révocation, la version d'étalonnage, une ancienneté maximale de 120 secondes et une avance maximale de 30 secondes. La qualité invalide ou la calibration requise n'est pas convertie en valeurs nulles assimilées à zéro : aucun nombre exploitable n'est créé. Les paquets refusés ne rafraîchissent pas la date des dernières mesures.

Le curseur `(appareil, session)`, le reçu unique `(appareil, session, séquence)` et la borne temporelle globale `transport_device_cursor` rendent le contrôle de rejeu durable. Changer de session ne permet pas de réinjecter un cumul ou une période déjà comptée. Le verrou de ligne de l'appareil sérialise l'ingestion concurrente sous PostgreSQL. Le rapport dérivé conserve bornes, durée et versions pour la provenance ; rapport, reçu, curseurs et fraîcheur sont validés dans une seule transaction. Aucun signal brut ni identifiant patient déclaré par l'émetteur n'est conservé.

## Commandes et preuves techniques

Le worker traite les jobs de calibration et mise à jour : `pending → sent → completed/failed/expired/blocked`. Une commande `skelivia.command.v1` contient le job, le type, l'appareil, un nonce aléatoire et une échéance de 120 secondes. Aucun succès n'est enregistré à l'envoi.

Un ACK `skelivia.ack.v1` doit venir du topic lié au certificat attendu et correspondre au job, type, appareil, nonce, preuve UUID et délai. Les droits du propriétaire, le périmètre support, le ticket attribué et l'autorisation temporaire de diagnostic sont revérifiés à la réception. Les réponses réelles, rejouées ou tardives sont refusées.

Une mise à jour exige en plus un correctif approuvé, sa version, le SHA-256 de l'artefact et une signature Ed25519 vérifiée. L'artefact fourni est explicitement **une fixture synthétique non flashable**, pas un firmware ESP32. Sa clé privée de signature n'est jamais montée dans le worker. Une signature de développement ne remplace pas une chaîne de publication matérielle de production.

Un ACK synthétique de calibration laisse `calibration_status=synthetic_reference` ; il ne débloque pas une clôture de ticket qui exige une preuve physique. Les jobs de remplacement/appairage et renouvellement de certificat restent en attente de leur installation et vérification matérielle. Les scripts opérateurs distincts couvrent le provisionnement de compte, la suppression et la révocation de certificat, avec leurs préconditions explicites ; le worker ne les exécute pas automatiquement et ne fabrique pas de preuve pour ces opérations.

## Révocation de certificat

Pour traiter un job approuvé dans le dashboard, l'adaptateur est en lecture seule par défaut :

```powershell
.venv/Scripts/python.exe scripts/prepare_infra.py --certificate-job <job-id>
.venv/Scripts/python.exe scripts/prepare_infra.py --certificate-job <job-id> --execute
```

L'exécution contrôle le demandeur sécurité actif, l'appareil et le numéro du certificat. Elle prépare la CRL, applique la révocation en base, redémarre uniquement le broker SKELIVIA puis exige un rejet TLS explicite `CERTIFICATE_REVOKED` avant de terminer le job. Une panne réseau n'est pas une preuve de révocation. En cas d'échec intermédiaire, le job reste `revocation_pending_disconnect`, reprend avec les mêmes préconditions et n'annonce aucun succès. Le renouvellement reste refusé par cet adaptateur tant que l'installation/appairage n'est pas vérifié.

La commande de bas niveau suivante prépare une révocation hors job et nécessite encore les étapes opérateur :

```powershell
.venv/Scripts/python.exe scripts/prepare_infra.py --revoke <CN-appareil>
docker compose -f infra/compose.yaml run --rm --no-deps -T migrate
docker compose -f infra/compose.yaml restart broker
```

La préparation ajoute le numéro du certificat à une CRL signée et marque le registre privé. La migration doit appliquer la révocation sans pouvoir l'annuler ; une rotation demande une procédure explicite. Le redémarrage du seul broker SKELIVIA coupe les connexions déjà ouvertes : une CRL ne suffit pas à interrompre une session TLS existante. Renouveler la CRL avant son expiration de 30 jours. La clé CA n'est pas accessible au broker.

## Sauvegarde et restauration

```powershell
.venv/Scripts/python.exe scripts/backup_restore.py backup
.venv/Scripts/python.exe scripts/backup_restore.py restore --file .runtime/backups/<archive>.skb
.venv/Scripts/python.exe scripts/prepare_infra.py --record-inventory
```

Le dump PostgreSQL transite en mémoire puis est chiffré et authentifié avec AES-GCM avant écriture. Une modification de l'archive ou une mauvaise clé est refusée avant création de base. La restauration crée exclusivement `skelivia_restore_<uuid>` ; elle ne peut cibler `skelivia`, `p2` ou une base préexistante. Aucune bascule automatique de l'application n'a lieu.

Avant remise en service, la politique actuelle est relue dans la source : tombstones de suppression exécutée, comptes désactivés et certificats révoqués. Les mesures et documents supprimés sont retirés de la restauration. Tous les partages, sessions et diagnostics restaurés sont révoqués par défaut ; les anciens jobs en attente sont mis en quarantaine. Une demande de suppression en attente ne vaut pas suppression effectuée. La restauration échoue fermée si la politique actuelle n'est pas disponible ; ce script ne prétend pas assurer une reprise après perte totale du site sans registre externe des révocations.

La clé des données reste nécessaire pour déchiffrer les champs après restauration. La sauvegarde de cette clé, l'isolement hors site, les rotations, la rétention, la restauration à un instant donné et les objectifs 15 minutes/4 heures restent des procédures d'exploitation à valider. Une copie chiffrée dans le même PC n'est pas une sauvegarde hors site.

## Vérifications réalisées sur le banc

- Tests ciblés ingestion/commandes/configuration/chiffrement/restauration/révocation, incluant faux ACK, répétition, données réelles, mauvais digest et suppression après restauration. Le workflow de révocation de job est testé sur base éphémère uniquement ; aucun certificat des souris actives n'est révoqué pour la recette.
- Broker vivant : absence de certificat refusée, publication sur son topic acceptée, publication sur un autre refusée, worker interdit de publier télémétrie, abonnements étrangers sans réception de données.
- Certificat de test dédié accepté avant révocation puis rejeté après CRL et redémarrage du broker.
- Parcours vivant PostgreSQL + worker + MQTT : mesure persistée sous le bon patient, commande de calibration reçue, faux nonce refusé puis ACK authentifié accepté, état conservé explicitement synthétique.
- Rejeu du même intervalle sous une nouvelle session refusé ; deux transactions PostgreSQL concurrentes sur la même période donnent exactement une acceptation et un rejet pour chevauchement. Correctif signé de test et ACK lié au digest vérifiés dans le worker réel.
- Sauvegarde AES-GCM et restauration PostgreSQL dans une base isolée effectuées le 14 novembre 2026. Les sessions et autorisations restaurées sont invalidées. Les essais des suppressions réappliquées utilisent en complément une fixture dédiée ; aucune suppression de compte du banc actif n'a été provoquée pour ce test.

Ces preuves ne remplacent pas la recette RLS/OIDC menée séparément, les essais matériels, l'AIPD, les obligations HDS ou PSC et une évaluation de sécurité complète. Le chiffrement applicatif protège les contenus sensibles, mais des métadonnées d'accès et de routage restent lisibles dans PostgreSQL. Le coffre local de fichiers n'est pas un KMS de production. Aucune sécurité « infaillible » n'est revendiquée.

## Versions et sources vérifiées

`infra/inventory-observed.json` contient les versions, identifiants des images effectivement démarrées et leur correspondance aux références configurées. Le champ `application_source_sha256` est un hash déterministe des fichiers Python sous `app/` dans le conteneur ; il ne couvre pas les fichiers statiques du frontend. L'inventaire est aussi enregistré dans les composants de l'administration. Les preuves de recette non secrètes sont regroupées dans `../verification/infra-live-results.json` ; `infra/verify_live.py` permet de rejouer la recette sur le banc préparé, avec le certificat de test révoqué dédié déjà présent.

Les images sont verrouillées par digest dans Compose : PostgreSQL 16.16, nginx 1.30.6, Mosquitto 2.1.2-alpine, Keycloak 26.7.5. La base Python 3.12-slim est également verrouillée. Les dépendances Python sont celles du lock commun, dont paho-mqtt 2.2.0 et cryptography 50.0.2. La vérification d'une version publiée n'est pas un audit de toutes ses vulnérabilités ; un suivi des correctifs reste nécessaire.

- [Mosquitto — configuration TLS, CRL et identité](https://mosquitto.org/man/mosquitto-conf-5.html)
- [Mosquitto 2.1.2](https://mosquitto.org/blog/2026/02/version-2-1-2-released/)
- [Keycloak — conteneurs et import de realm](https://www.keycloak.org/server/containers)
- [Keycloak — proxy et hostname](https://www.keycloak.org/server/hostname)
- [Keycloak 26.7.5](https://www.keycloak.org/2026/09/keycloak-2675-released)
- [PostgreSQL — versions maintenues](https://www.postgresql.org/support/versioning/)
- [nginx — versions publiées](https://nginx.org/en/download.html)
- [Paho MQTT sur PyPI](https://pypi.org/project/paho-mqtt/)
- [Cryptography sur PyPI](https://pypi.org/project/cryptography/)
