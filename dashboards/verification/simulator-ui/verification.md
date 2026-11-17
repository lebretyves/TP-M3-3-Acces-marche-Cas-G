# Recette frontend du simulateur

Brief appliqué : `dashboards/simulateur/BRIEF.md`. Interface réalisée dans `dashboards/simulateur/static/`, distincte de l’application métier et utilisant ses seuls assets de marque autorisés. Aucun résultat de mesure n’est codé en dur dans le frontend.

Le catalogue et les résultats proviennent du moteur. L’aperçu et la transmission sont séparés. La réception MQTT est nommée « acceptée par le broker » et ne vaut pas preuve d’écriture en base. Le rejeu sans hypothèses conserve les valeurs de contact et d’appuis invalides ; les relevés balance restent une référence distincte. La coupure réseau s’applique à toute l’exécution ; la reprise nécessite un scénario Normal. Les états préparation, arrêt en cours et calibration requise sont explicités.

## Vérifications

- `../test-simulator-ui.cjs` : 14 contrôles réussis. Transport HTTP contrôlé, calculs générés par le vrai moteur Python. Aucun envoi MQTT. Scénarios, rejeu, hypothèses explicites, mode manuel, aperçu, démarrage/pause/reprise/arrêt, rapport, refus CSRF et transport absent.
- `../test-simulator-live-preview.cjs` : 3 contrôles réussis sur le serveur réel `127.0.0.1:8774`. Aperçus Wokwi et phyphox uniquement, sans démarrage d’exécution ni modification du transport.
- Les états principaux sont vérifiés à 320, 390, 768 et 1440 px : aucun débordement horizontal global, commandes d’au moins 44 × 44 px. Les tableaux défilent dans leurs conteneurs. Texte courant 16 px, métadonnées 14 px, identité SKELIVIA conservée.
- Captures inspectées sur ordinateur et téléphone. Les captures `live-preview-*` proviennent de l’API réelle ; les autres utilisent le transport contrôlé de la recette.

Les fichiers `results.json` et `live-preview-results.json` détaillent les contrôles. Cette recette frontend ne prouve ni la réception clinique, ni une livraison de notifications, ni le fonctionnement sur chaque appareil physique. L’évaluation visuelle indépendante reste à effectuer.
