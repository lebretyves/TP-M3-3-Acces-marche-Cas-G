# Recette de l'application SKELIVIA

14 novembre 2026 — application intégrée, données fictives, projet Docker `skelivia` uniquement. Les résultats de la maquette séparée ne sont pas comptés comme des preuves de sécurité applicative.

| Contrôle | Résultat | Preuve |
|---|---|---|
| Suite Python finale | 110 réussis, 5 essais Docker explicitement ignorés dans cette commande standard | [JUnit](application-tests.xml) |
| Dépendances Python | `pip check` réussi | `requirements.lock.txt` et environnement `.venv` du projet |
| Autorisations PostgreSQL réelles | 15 réussis sous `skelivia_app` non propriétaire ; mutations annulées | [Rapport](postgres-access-results.json) |
| Authentification finale | Les cinq rôles et le second approbateur connectés par Keycloak + OTP ; API workspace accessible | [Rapport OIDC](captures/verification-oidc-live.json) |
| TLS/MQTT/ingestion/commandes | Validation stricte CA interne, mTLS/ACL/révocation, rejeu et concurrence, nonce et digest des ACK vérifiés | [Recette Docker](infra-live-results.json) |
| Sauvegarde/restauration | Archive chiffrée, restauration isolée, autorisations révoquées et politique courante réappliquée | [Recette Docker](infra-live-results.json) |
| Inventaire final | Sept services exécutés correspondant aux images déclarées | [Inventaire](../application/infra/inventory-observed.json) |
| Revue visuelle indépendante finale | PASS ; 72 états examinés, sans erreur JavaScript ni débordement global | [Revue 2](evaluation-application-2.md) |
| Lisibilité et clavier | 43 contrôles réussis, cinq rôles et texte agrandi, commandes principales de 44 px | [Vérifications](readability-refinement/verification.md) |
| Mesures | Pagination réelle, dates avant limite, export jamais tronqué silencieusement, pondération explicitée | [API/responsive](pagination-live-results.json), [contrats UI](measures-frontend-results.json) |
| Notifications | Configuration désactivée correctement indiquée ; aucun envoi ni permission automatique | [Intégration](push-integration-results.json), [contrats UI](push-frontend-results.json) |

Les cinq essais ignorés par la suite Python standard sont les essais explicitement réservés au broker et au worker Docker. Ils ont été exécutés séparément sur ce banc, comme décrit dans `infra-live-results.json`. Le warning Starlette sur le transport de son client de test est une dépréciation ; il n'a pas causé d'échec.

Les comptes opérateur et OTP de recette sont privés, hors rapports et captures. Les connexions de recette navigateur acceptent le certificat local pour ce test ; elles ne prouvent pas la confiance TLS du poste, où l'interception Norton est documentée. Les connexions internes vérifient effectivement la CA. Les serveurs temporaires d'application QA sur 8772/8773 ont été arrêtés après vérification ; l'application principale reste sur `https://localhost:8443`.

Cette recette n'atteste pas un déploiement clinique, une homologation matérielle, un raccordement PSC/HDS ou une réception sur une montre physique. Voir les [limites et étapes externes](../application/ARCHITECTURE_ET_RECETTE.md). Les durées d'une restauration locale ne constituent pas une garantie RPO/RTO.

Aperçus de la version finale : [utilisateur sur ordinateur](captures/oidc-u-alice.png) et [revue mobile/tablette](application-eval-2/).
