# Extension événements et actions — 15 novembre 2026

Le simulateur conserve son moteur Wokwi/phyphox et son transport MQTT mTLS. Les événements sélectionnés utilisent une extension facultative et stricte de `skelivia.telemetry.v1`. L'ingestion crée la notification et le rapport dans la même transaction, après vérification de l'identité, de la qualité et de l'absence de rejeu. Les préférences sont lues par le worker ; aucune lecture de documents médicaux n'est ajoutée à ce rôle SQL.

Le panneau propose 37 actions correspondant aux 33 commandes métier existantes (préférences déclinées en trois formulaires) et aux deux exports autorisés. Les cinq parcours préparent leurs étapes individuellement. La fenêtre de l'application conserve les droits de la session, le contrôle du persona choisi, le CSRF, les réauthentifications et les approbations distinctes. Le simulateur ne reçoit aucun token, workspace ou document exporté.

## Vérifications effectuées

- **88 tests du simulateur réussis**, sans test ignoré : moteur, contrat transport, sélection des événements, file manuelle, erreur de publication, absence de datation rétroactive et catalogue. [Rapport JUnit](../verification/simulator-actions-tests.xml).
- **139 tests applicatifs et d'autorisation réussis**, cinq tests d'infrastructure conditionnels non exécutés par cette commande locale : [rapport JUnit](../verification/application-actions-tests.xml). Les vérifications réelles PostgreSQL/MQTT effectuées séparément sont décrites ci-dessous.
- **15 contrôles PostgreSQL réussis** avec l'identité non propriétaire `skelivia_app` : huit espaces de compte, partages et révocation, séparation des organisations, support et expiration des diagnostics, routage des tickets, suppression de rappels, approbateur distinct et chiffrement. Mutations de ces contrôles annulées.
- **Recette réelle avec les cinq personas** : préférence de pause, création de ticket, partage, conseil soignant, réponse support, export employeur, contrôle sécurité et révocation du partage. Les conseils et réponses produisent leurs notifications. Les comptes utilisent OIDC et MFA, sans dérogation d'autorisation. [Résultats](../verification/simulator-actions-live/results.json).
- **Intensif 30 secondes** : six reçus PostgreSQL, une notification de pause calculée. **Appuis élevés 5 secondes** : un reçu, une notification d'appui calculée. **Normal avec injection manuelle d'absence** : un reçu, une notification portant la mention Simulation manuelle. Ces trois notifications ont été retrouvées dans le workspace utilisateur. [Preuve base en lecture seule](../verification/simulator-actions-live/database-proof.json).
- **12 contrôles d'interface avec API contrôlées** : champs, types, rôle, dates, listes autorisées, absence de mutation automatique et états d'erreur. [Résultats](../verification/simulator-actions-ui/results.json).
- **Évaluation visuelle indépendante PASS** : neuf contrôles, 17 captures, aucun débordement ni erreur JavaScript aux formats examinés. [Captures](../verification/simulator-actions-eval-1/).

## Limites conservées

Une réception MQTT n'est pas une confirmation de notification. Les notifications répétées d'un même type sont limitées à une par minute et par souris. Les rappels de pause nécessitent l'activation des pauses et respectent leur report. Les injections restent explicitement manuelles ; elles ne modifient pas les mesures calculées. Une fenêtre invalide n'émet pas d'événement d'usage valide. Une injection attend la prochaine fenêtre valide ; si l'exécution se termine avant, elle est annulée dans le rapport. En cas d'accusé MQTT manquant, les tentatives sont conservées avec une réception non confirmée.

Web Push demeure désactivé dans la configuration du banc. Aucun téléphone ou montre n'a reçu de notification pendant cette recette. Les événements d'appui, d'immobilité et d'absence restent internes au dashboard. Aucun seuil médical ni calibration physique n'est validé par ces tests.

Le lancement d'une action métier peut créer une demande en attente : installation de mise à jour, remplacement, calibration, certificat, provisionnement ou suppression nécessitent toujours leur adaptateur et leur preuve. Les sauvegardes et restaurations restent des opérations d'infrastructure, pas des preuves fabriquées par le simulateur. La recette a laissé un ticket et un conseil explicitement fictifs ; son partage temporaire a été révoqué.

## Consulter les preuves

Le script `application/scripts/verify_usage_events.py --run UUID` ne s'exécute qu'avec le rôle PostgreSQL opérateur prévu et impose une transaction en lecture seule. Il renvoie uniquement les compteurs, types, origines et statuts des événements, sans valeur de mesure, contenu médical ni secret.

L'interface est disponible sur <http://127.0.0.1:8774>. Les actions ouvrent une fenêtre sur <https://localhost:8443>. Après une mise à jour des sources applicatives, reconstruire l'image et appliquer `app.bootstrap` avant de redémarrer les services concernés ; le lanceur seul ne reconstruit pas une ancienne image.
