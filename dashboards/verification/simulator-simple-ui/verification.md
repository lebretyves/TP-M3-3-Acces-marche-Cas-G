# Simulateur simple — interface sur une page

Contrôles Playwright avec réponses API contrôlées, indépendants de la recette réelle du banc.

17 contrôles réussis :

- Six scénarios immédiatement visibles ; trois courbes affichées, options détaillées repliées.
- Choix Intensif puis Lancer : mode et durée corrects, sans configuration supplémentaire.
- Temps et valeurs repris des réponses serveur, sans données inventées par l’interface.
- Pause : retour au temps de la dernière fenêtre complète fourni par le service.
- Événement local visible sans affirmer sa réception dans le dashboard.
- Mise en page sans débordement à 1440, 768, 390 et 320 pixels.
- Nouveau choix hors exécution : anciennes courbes effacées.
- Valeurs invalides affichées comme inconnues, sans remplacement par zéro.
- Mode local disponible sans transport configuré.
- Formulaire d’action intégré dans la page : aucune fenêtre supplémentaire ouverte.
- Connexion avec retour `/simulateur/` dans la page principale.
- Action de préférences exécutée avec le compte authentifié simulé.
- Autre persona bloqué sans action métier envoyée.
- Wokwi chargé seulement après clic, dans un cadre protégé ; pas de couplage annoncé avec le moteur local.
- Service indisponible signalé et lancement désactivé.
- Aucune erreur JavaScript observée.

Les trois fichiers JavaScript passent également `node --check`.

Captures : `intensive-{1440,768,390,320}.png`, `actions-{1440,390,320}.png`, `wrong-role.png`, `service-unavailable.png`. Résultat : `results.json`.

Ces tests utilisent des réponses API contrôlées. Ils ne constituent pas une preuve MQTT, d’écriture en base, de réception de notification réelle ou d’exécution distante de Wokwi. La recette réelle et l’évaluation indépendante sont distinctes.
