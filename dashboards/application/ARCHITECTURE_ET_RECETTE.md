# Architecture de référence et portée de la recette

État du livrable local : 14 novembre 2026. Ce document complète le PDF, sans modifier rétroactivement ses constats du 13 novembre.

## Référence retrouvée

[Proposition_architecture_securisee_personas_P2.pdf](../../outputs/P1_ARCHITECTURE_SECURISEE_20261113/Proposition_architecture_securisee_personas_P2.pdf), 28 pages, SHA-256 `5B43275B2C6CC0CE7A84D34B6982D61E8706A541294C311F2FA0E44C906731D7`.

Les copies dans `work/p1_sauvegarde_collecte_20261112/projet1/architecture_cible` et `outputs/P1_STACK_OBLIGATIONS_20261113` portent la même empreinte. Le nouveau code est isolé dans `dashboards/application`. Le P1, l'ancien banc P2 et les autres projets Docker sont conservés.

## Correspondance aux décisions d'architecture

| Référence | Réalisation | Portée |
|---|---|---|
| Pages 1–5 : quatre métiers et sécurité séparée | Cinq interfaces, un backend modulaire, rôle issu du compte serveur, autorisations par relation/organisation/partage/attribution | API persistante et RLS PostgreSQL, aucun changement de rôle par navigateur |
| Pages 2, 15 : trajet et contrôle des données | mTLS/ACL → worker → PostgreSQL privé → API autorisée → interface | Contrat synthétique d'intervalles, sans signal brut ni diagnostic automatique |
| Pages 6, 9–10 : fraîcheur, absence et alerte | Données anciennes signalées, paquet invalide ne rafraîchit pas l'état, fenêtres non superposées, cumul incomplet interdit | Ne permet pas d'inférer repos, sédentarité ou absence de risque |
| Pages 7, 17 : minimisation et cycle de vie | Payloads sensibles chiffrés, partages bornés, révocation, demande de suppression et opérateur hors ligne | Conservation et obligations externes exigent une politique décidée ; métadonnées techniques non entièrement chiffrées |
| Pages 8, 10 : infrastructure et reprise | Compose isolé, port HTTPS local unique, sauvegarde chiffrée, restauration dans une base dédiée | Aucun hébergeur clinique choisi ; pas de bascule automatique ni garantie RPO/RTO |
| Page 18 : identité et sécurité | OIDC/PKCE/MFA, sessions serveur, contrôle des jetons et du logout, réauthentification pour actions sensibles | Keycloak local ; PSC et récupération d'identité professionnelle non raccordés |
| Page 19 : interopérabilité | Adaptateur FHIR R4 de test, Patient/Observation, unités UCUM, provenance synthétique | Aucun profil destinataire/CI-SIS validé, aucun échange clinique externe |
| Pages 20–21 : réutilisation et travaux manquants | Frontend simple cohérent Atelier, backend P2 adapté, modules ingestion/domaine/notifications, scripts opérateur | Aucun import global d'un autre projet ni migration de ses données |

## Recette T01 à T18

« Banc » désigne les comptes, mesures et appareils synthétiques. Un test logiciel ne prouve pas la sécurité électrique, la calibration physique ni l'efficacité clinique.

| Test PDF | Preuve disponible | Limite restante |
|---|---|---|
| T01 — utilisateur A/B | Tests domaine et sondes PostgreSQL sous rôle applicatif : lectures et exports isolés | Refaire sur configuration de déploiement finale |
| T02 — soignant non lié | Relation, dates, catégories et partage actif exigés côté API et RLS | Identité professionnelle externe à valider |
| T03 — retrait d'un partage | Requête suivante refusée, curseur lié au périmètre, UI revalidée et contenu fermé | Une copie déjà téléchargée ne peut être rappelée |
| T04 — employeur/support | JSON et actions filtrés ; support attribué avec accord temporaire propriétaire | Le texte libre ne détecte pas automatiquement toute saisie médicale abusive |
| T05 — organisation/double rôle | Compte avec rôle unique, contrôle d'organisation et périmètre ; approbation distincte des changements | Pas de cumul automatique de profils ni changement de contexte multi-rôle |
| T06 — certificat/topic | Essais broker vivant : mTLS, ACL, certificat révoqué ; registre applicatif vérifié | Provisionnement et rotation d'un vrai appareil à réaliser |
| T07 — vieux paquet/rejeu/valeur | Tests de temps, séquence, fenêtre, doublons, qualité, bornes et concurrence PostgreSQL | Aucun signal matériel réel validé |
| T08 — coupure/reconnexion | Fraîcheur projetée depuis les données reçues, heartbeat worker/MQTT, ancien paquet refusé | Pas de campagne de panne réseau terrain ni preuve de service cloud |
| T09 — message/notification | Événements internes persistants, Web Push générique, essais de file/retry/410/révocation/horaires | Livraison réelle téléphone/montre non activée ni démontrée |
| T10 — petit groupe employeur | Aucune mesure de santé, individuelle ou agrégée, dans cet espace | Pas de fonction d'agrégation à certifier |
| T11 — restauration isolée | Archive AES-GCM et restauration réelle PostgreSQL dans `skelivia_restore_<uuid>` | Objectifs 15 min/4 h, hors site et exercice de perte totale non démontrés |
| T12 — session/MFA | Connexion Keycloak mot de passe+OTP sur les cinq rôles ; expiration/inactivité/suspension testées ; réauth récente | Récupération MFA après vérification d'identité à encadrer par l'opérateur |
| T13 — administration normale | Absence de lecture médicale ; refus d'auto-approbation, règles serveur et RLS | Audit indépendant de sécurité de production restant |
| T14 — accès exceptionnel | Approbateur distinct pour droits, diagnostic support limité et expirant, traces sans contenu médical | Aucun contournement exceptionnel médical ajouté ; procédure d'urgence et récupération à spécifier si requises |
| T15 — FHIR destinataire | Tests unités/sujet/qualité/provenance sur Bundle R4 synthétique | Pas de validateur du profil choisi ni de destinataire raccordé |
| T16 — suppression/restauration | Opérateur transactionnel, preuve et tombstone ; restauration réapplique les suppressions et révoque les accès | Politique de conservation, IdP, CRL et fin de rétention des archives demeurent des étapes explicites |
| T17 — versions/mise à jour | Lock Python, images par digest, évaluation/approbation distinctes, signature et digest de commande testés | Fixture non flashable ; ni secure boot ni mise à jour physique attestés |
| T18 — compromission | Révocation de sessions, suspension approuvée, registre/CRL, incidents et traces techniques | Exercice organisationnel de notification et réponse hors site à conduire |

Les rapports et scripts sont conservés dans [verification](../verification/). Les sondes de droits PostgreSQL sont dans `app/verify_domain_pg.py` ; leurs mutations de recette sont annulées. Les tests broker/worker sont explicitement activables et ne doivent viser que ce banc.

## Activation externe restant nécessaire

- Choisir l'hébergement, le domaine et le responsable d'exploitation ; configurer un certificat reconnu, sauvegardes hors site et gestion des clés. Le port actuel est limité à `127.0.0.1`.
- Arrêter la finalité, les responsabilités, la conservation et les décisions réglementaires applicables du PDF ; ne pas déduire une conformité d'un test technique.
- Raccorder PSC si applicable, organiser l'enrôlement et la récupération MFA avec vérification d'identité. L'opérateur de provisionnement prépare des comptes désactivés ; il ne fabrique pas un enrôlement réalisé.
- Fournir le matériel et le firmware réels, puis vérifier calibration, appairage, rotation des certificats, chaîne de mise à jour, sécurité physique et usage.
- Définir le contact VAPID et le réseau de sortie avant activation des notifications, puis tester les appareils réellement utilisés. Les réglages de canal seuls ne constituent pas une preuve de livraison.
- Convenir des profils et du destinataire FHIR/CI-SIS et exécuter leur recette avant tout échange concerné.

Le dispositif de surveillance détecte certains signaux techniques (nouvel appareil dans le dashboard, refus répétés d'authentification applicative, actions interdites répétées, absence de heartbeat). Il ne constitue pas un IDS couvrant tous les journaux, tous les équipements ou toutes les menaces. La protection brute force de Keycloak est distincte ; ses échecs de saisie ne sont pas tous retransmis au dashboard. Les preuves de sauvegarde sont bornées à l'opération effectuée.
