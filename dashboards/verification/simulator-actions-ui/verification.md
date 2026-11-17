# Interface du simulateur — événements et actions

Vérification de l’interface avec Playwright et réponses API contrôlées. Ces essais ne prouvent pas une mutation réelle en base ni une livraison de notification externe.

- Affichage du simulateur à 1440, 768, 390 et 320 px, sans débordement horizontal.
- Fenêtre d’action à 920, 390 et 320 px, sans débordement horizontal.
- Quatre événements automatiques sélectionnés par défaut.
- Sélection d’une étape guidée : choix du persona et de l’action correspondants.
- Compte d’un autre persona : action bloquée et aucune mutation automatique.
- Réponse à un ticket via le formulaire : action et paramètres attendus.
- Le contenu de la réponse reste dans la fenêtre applicative ; il n’apparaît pas dans l’historique du simulateur.
- Préférences de notifications : construction de `channels.pause` comme propriété imbriquée, sans champ plat parasite.
- Dates par défaut : jour UTC courant.
- Injection manuelle : confirmation d’attente, sans affirmation de réception dans le dashboard.
- Catalogue indisponible : erreur explicite, indépendante du simulateur de mesures.
- Aucune erreur JavaScript observée.

Résultat détaillé : `results.json`. Captures : `simulator-*.png`, `bridge-*.png`, `catalogue-unavailable.png`.

Le pont vérifie l’origine, la fenêtre émettrice et un nonce propre à l’action. Il exige le persona choisi et relit la session avant chaque mutation. Une réception de message n’exécute jamais l’action : un clic dans la fenêtre authentifiée est requis. Les API métier restent l’autorité pour les droits, prérequis et transitions.

Les tests de bout en bout avec authentification réelle et les preuves MQTT/base sont menés séparément par l’agent principal.
