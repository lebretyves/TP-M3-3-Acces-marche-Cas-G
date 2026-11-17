# Vérification des corrections de lisibilité

Corrections ciblées de `evaluation-application-1.md`, en conservant la direction visuelle validée. Brief appliqué : `dashboards/conception/brief-application.md`.

- Texte courant et commandes : 16 px au minimum ; métadonnées : 14 px. La préférence d’agrandissement porte la base à 18 px.
- Commandes partagées et sélecteur Jour / Semaine / Mois : cibles d’au moins 44 × 44 px, indépendamment du type de pointeur détecté.
- Menu mobile : sélection de la liste complète des éléments, garde si liste vide, confinement Tab / Maj+Tab et restitution du focus avec Échap.
- Ticket mobile : retour à la liste sur une ligne distincte, séparée du statut.
- Appareil sans date : « État inconnu » ; données anciennes : état ambre « Données anciennes ».

Recette automatisée : `../test-readability-refinement.cjs`, 43 contrôles réussis, aucune erreur JavaScript et aucun texte observé sous 14 px. Les cinq rôles et toutes leurs rubriques ont été parcourus aux largeurs 320, 390, 768 et 1440 px. Les boucles clavier sont vérifiées pour chaque rôle ; le texte agrandi est contrôlé à 320 × 568 et 768 × 568. Aucun débordement global observé. Le dossier patient actif et le détail du ticket sont inclus dans les captures.

Les réponses HTTP sont simulées dans le test à partir du contrat, exclusivement dans Playwright : aucune fixture n’est ajoutée à l’application, aucune connexion réelle n’est consommée et aucune donnée persistante n’est modifiée. Ces résultats ne remplacent pas la seconde évaluation indépendante sur l’application authentifiée ni un essai sur appareils physiques. Les preuves détaillées sont dans `results.json` et les captures PNG de ce dossier.
