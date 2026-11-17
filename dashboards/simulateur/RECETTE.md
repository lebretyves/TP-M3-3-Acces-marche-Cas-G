# Recette du simulateur — 14 novembre 2026

Le simulateur a été réalisé et raccordé à l'application locale. Les sources physiques restent des références ; toutes les fenêtres publiées sont déclarées synthétiques.

- **41 tests Python réussis**, zéro ignoré : moteur22, serveur7, infrastructure/transport12. Rapport : [JUnit](verification-tests.xml).
- **4 200 échantillons comparés au C++ natif** compilé depuis la référence `pipeline.h` : sept modes, compteurs gyro, états, appuis relatifs et événements de démonstration.
- **Trois rejeux phyphox** : usage souris, postures/pauses, comptage indépendant. Tests des lacunes, pondération temporelle, hypothèses explicites et empreintes de fichiers.
- **Scénario Normal, dix secondes** : deux messages acquittés MQTT et deux rapports synthétiques valides retrouvés séparément en PostgreSQL. [Preuve du transport](../verification/simulator-transport-live.json).
- **Dashboard authentifié** : les deux identifiants de rapport sont visibles par Alice via l'API autorisée et l'écran des mesures. [Preuve](../verification/simulator-dashboard-results.json), [ordinateur](../verification/simulator-dashboard-1440.png), [téléphone](../verification/simulator-dashboard-390.png).
- **Mesure invalide, cinq secondes** : rapport reçu avec qualité invalide, sans faux zéro. **Rejeu phyphox avec hypothèses d'appui/contact**, cinq secondes : un rapport synthétique reçu, hypothèses conservées dans le rapport de simulation. [Preuves complémentaires](../verification/simulator-extra-live.json).
- **Interface** : 14 contrôles avec réponses contrôlées et moteur réel, trois contrôles sur API réelle, sans publication pour ces tests d'interface.
- **Revue visuelle indépendante : PASS**, 20 captures, aucun débordement global ni erreur JavaScript sur les formats examinés. [Rapport](../verification/evaluation-simulateur-1.md), [captures](../verification/simulator-eval-1/).

Le serveur du simulateur ne détient aucun secret PostgreSQL, aucune clé de CA privée et ne publie qu'avec l'identité de l'appareil de banc prévu. L'accès web est lié exclusivement à `127.0.0.1:8774`. Les commandes intersites et champs de configuration non autorisés sont refusés.

La préparation de la référence `synthetic_reference` a utilisé le parcours existant de commande/nonce/ACK synthétique authentifié, sans flash ni calibration physique déclarée. Une autre calibration requise n'est pas effacée automatiquement par le lanceur : elle conduit à des fenêtres `calibration_required` sans valeurs.

La colonne « accepté par le broker » du panneau n'est pas une preuve de persistance. Les vérifications PostgreSQL ci-dessus ont été réalisées séparément par l'opérateur. Les événements Wokwi ne constituent ni des diagnostics ni de nouvelles notifications médicales dans les dashboards. Les profils émulés ne remplacent pas les essais sur tous appareils physiques.
