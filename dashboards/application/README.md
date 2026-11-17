# SKELIVIA — application intégrée

Application locale avec cinq espaces : utilisateur, soignant, employeur/prévention, support et administration sécurité. Le frontend utilise les fonctions validées dans la [conception](../conception/Propositions_personas_donnees_securite.md), le logo original, les titres inclinés, la navigation marine et les accents turquoise/bleu. Les compteurs de statut sont colorés et restent accompagnés de leur libellé.

Le [simulateur séparé](../simulateur/README.md) peut maintenant alimenter le banc d'Alice avec les scénarios Wokwi et des rejeux phyphox explicitement synthétiques. L'outil [d'accès de recette](../Afficher%20acces%20de%20recette%20SKELIVIA.cmd) affiche désormais les codes temporaires avec renouvellement automatique et compte à rebours.

Le banc fonctionne avec des données fictives, des comptes séparés et de véritables contrôles serveur. Il ne constitue pas une mise en service clinique. Le contrat d'ingestion refuse les données déclarées réelles : aucun contournement de ce verrou n'est prévu dans ce livrable.

## Ouvrir

Sur ce poste, Docker Desktop doit être démarré. Double-cliquer sur [Ouvrir application SKELIVIA.cmd](../Ouvrir%20application%20SKELIVIA.cmd), puis ouvrir **https://localhost:8443**. Le lanceur démarre uniquement le projet Compose `skelivia` et n'efface aucune donnée.

Le certificat HTTPS est signé par la CA privée du banc. Celle-ci n'est pas installée automatiquement dans Windows. Le navigateur peut donc afficher un avertissement de confiance. Le certificat public est `.runtime/infra/pki/public/ca.pem` ; son empreinte se consulte avec `certutil -hashfile .runtime/infra/pki/public/ca.pem SHA256`. Pour un service accessible à d'autres appareils, il faudra un domaine, un certificat reconnu et un déploiement configuré : ce port reste volontairement limité à ce PC.

Sur ce poste, les essais ont aussi observé une interception HTTPS de Norton sur `localhost:8443`, avec un certificat de remplacement non reconnu. La vérification stricte TLS réussit à l'intérieur du réseau Docker. La confiance du navigateur hôte doit donc être réglée par l'opérateur ; le lanceur ne désactive ni TLS ni la protection du poste.

Le bouton de connexion mène à Keycloak, avec mot de passe puis code temporaire. Les comptes de recette sont :

| Espace | Identifiant Keycloak |
|---|---|
| Utilisateur | `u-alice` |
| Soignant | `c-lina` |
| Employeur/prévention | `e-atelier` |
| Support | `t-support` |
| Administration sécurité | `s-securite` |
| Approbateur sécurité distinct | `s-approbateur` |

Les secrets de recette restent dans `.runtime/`, exclu du dépôt. Ouvrir [Afficher les accès de recette](../Afficher%20acces%20de%20recette%20SKELIVIA.cmd), ou lancer explicitement `scripts/show_test_access.py` avec le Python `.venv`, pour les consulter sur ce PC. Cet outil affiche des secrets : ne pas partager sa sortie. Les clés OTP de recette stockées sur ce même poste ne démontrent pas l'indépendance des facteurs en exploitation. Les comptes supplémentaires `u-benoit` et `c-marc` servent aux essais d'isolation.

## Architecture réalisée

Le [PDF de référence](../../outputs/P1_ARCHITECTURE_SECURISEE_20261113/Proposition_architecture_securisee_personas_P2.pdf) a été retrouvé et relu. La [traçabilité](ARCHITECTURE_ET_RECETTE.md) distingue ce qui est implémenté, testé sur le banc et encore dépendant d'une décision ou d'un équipement externe.

- Un backend Python FastAPI modulaire commun ; les droits sont vérifiés à chaque requête, sans sélecteur de rôle dans le produit.
- PostgreSQL privé avec politiques RLS et identités SQL distinctes pour l'API, l'ingestion, les notifications et les migrations.
- Keycloak OIDC, PKCE et MFA ; sessions opaques côté serveur, protection CSRF, contrôle d'origine, expiration et révocation.
- Broker Mosquitto privé avec TLS mutuel, certificat par appareil, ACL par topic, rejet du rejeu et des intervalles qui se chevauchent.
- Worker d'ingestion et de commandes : un clic crée une demande, seul un accusé de réception vérifié peut changer son résultat technique.
- Chiffrement des contenus sensibles en base et des archives de sauvegarde, clés séparées des données, journaux sans contenu médical.
- Web Push avec file persistante et notifications génériques ; l'envoi externe est désactivé tant que le contact VAPID et le réseau de sortie ne sont pas configurés.

Le support consulte uniquement ses tickets et diagnostics techniques autorisés et temporaires. L'employeur n'accède ni aux mesures individuelles ni aux dossiers médicaux. L'administration sécurité n'a pas d'accès médical normal et ne peut pas s'attribuer seule un rôle soignant.

## Fonctionnement et limites utiles

Les partages, révocations, conseils versionnés, bilans, recommandations, tickets, préférences, sessions, demandes et incidents sont persistants. La comparaison des mesures indique les changements de calibration ; les pages incomplètes ne produisent pas de faux cumul. Les exports filtrent la période avant de limiter le volume et refusent un résultat incomplet.

Les interfaces sont adaptées aux téléphones, tablettes et ordinateurs. Les essais utilisent Chromium et WebKit avec plusieurs dimensions ; ils ne remplacent pas une recette sur chaque appareil iPhone, Android ou Mac physique. Le service local n'est pas exposé au réseau du téléphone.

Les rappels sur montre utilisent le relais du téléphone et du système lorsqu'il est disponible. Une livraison indépendante « montre seule » n'est pas annoncée comme prise en charge. Un abonnement navigateur exige une action explicite ; aucune permission de notification n'est demandée automatiquement.

La calibration, l'appairage d'une souris de remplacement et l'installation d'un firmware réel exigent leur preuve matérielle. Les fixtures de firmware sont marquées non flashables. Les états en attente ne sont pas transformés en succès fictifs. La suppression dispose d'un opérateur hors ligne, en simulation par défaut, exigeant une référence de politique de conservation ; sa preuve distingue la base applicative des obligations IdP, certificats et archives.

L'adaptateur FHIR R4 produit un Bundle de test synthétique avec unités et provenance. Il ne prétend pas être conforme au profil CI-SIS d'un destinataire non encore choisi. Il n'ajoute pas l'export soignant refusé lors de la conception.

## Fichiers et exploitation

| Dossier / document | Contenu |
|---|---|
| `app/static/` | Interfaces, styles, logo, police locale, manifeste et service worker sans cache médical |
| `app/` | Authentification, domaine, autorisations, ingestion, notifications, FHIR |
| `infra/` | Compose isolé, proxy, broker et image verrouillée |
| `scripts/` | Préparation, sauvegarde/restauration et opérations hors ligne |
| `tests/` | Tests applicatifs, sécurité et intégration autorisée |
| [INFRA.md](INFRA.md) | Démarrage complet, secrets, mTLS, sauvegardes et restauration |
| [API_CONTRACT.md](API_CONTRACT.md) | Actions, droits et correspondance aux décisions fonctionnelles |
| [PUSH_CONTRACT.md](PUSH_CONTRACT.md) | Conditions d'envoi et limites téléphone/montre |
| [ARCHITECTURE_ET_RECETTE.md](ARCHITECTURE_ET_RECETTE.md) | Référence PDF, preuves et prérequis externes |
| `../verification/` | Scripts de parcours, rapports et captures |

Tests locaux depuis ce dossier :

```powershell
.venv/Scripts/python.exe -m pytest -o addopts='' -q
.venv/Scripts/python.exe -m pip check
docker compose -f infra/compose.yaml config --quiet
```

Les essais vivants broker/worker nécessitent des options explicites et le banc Docker ; ils sont ignorés dans la commande standard. Ne pas utiliser une base réelle de patients pour les lancer.

La [recette finale](../verification/RECETTE_APPLICATION.md) regroupe 110 tests Python réussis, 15 contrôles PostgreSQL réels, les connexions OIDC/MFA des cinq rôles et la revue visuelle indépendante validée après correction. Les essais Docker et leurs limites sont conservés séparément.

Les objectifs de reprise 15 minutes / 4 heures du PDF ne sont pas déclarés atteints par une seule restauration isolée. L'hébergement, les obligations HDS/PSC applicables, la conservation, l'AIPD, les profils d'échange et la validation physique/clinique restent à finaliser avant le traitement concerné. Aucune sécurité « infaillible » n'est revendiquée.
