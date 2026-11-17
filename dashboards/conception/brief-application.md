# SKELIVIA — intégration applicative et recette visuelle finale

L'utilisateur a demandé de terminer tout le projet selon le PDF retrouvé, après validation des fonctions et de la direction visuelle. Ce mandat remplace les restrictions « maquette seulement » du brief précédent. L'application est `dashboards/application/app/static/index.html`, servie par FastAPI avec authentification, rôle serveur, API persistante et contrôles d'accès. La maquette de référence reste séparée.

Les décisions oui/non de `Propositions_personas_donnees_securite.md` restent la source fonctionnelle. Le contrat intégré est `../application/API_CONTRACT.md`. Aucune fonction refusée, aucun export soignant, aucun sélecteur de rôle, aucune donnée médicale employeur/support/admin. Les demandes techniques attendent une preuve vérifiée, pas un faux succès.

Direction visuelle approuvée : logo original intact, titres Orbitron 900 inclinés modérément, texte courant Segoe UI ; fond blanc/gris, menu vertical bleu marine, accents turquoise et bleu, formes simples peu arrondies. Compteurs employeur ambre/bleu/vert/rouge avec libellés. Logo local et police locale, aucun autre visuel nécessaire. L'identité SKELIVIA et les titres doivent rester lisibles, sans effet décoratif envahissant.

Structures approuvées : utilisateur état souris/calibration puis mesures et conseils/bilan ; soignant liste de patients et rappels latéraux ; employeur compteurs et tableau de recommandations ; support tickets et détail latéral, page dédiée mobile ; sécurité alertes puis correctifs et protections latérales. Barre haute titre à gauche, notifications/compte à droite. Navigation mobile repliable.

Vérifier les cinq espaces en bureau, téléphone étroit et tablette, y compris une sous-vue et un formulaire représentatifs. Dimensions 320/390/768/1440 ; pas de débordement horizontal global, cibles tactiles, labels/focus, contrastes, texte courant 16px. Les grands titres anguleux ne doivent pas couper les mots. Tableaux peuvent défiler dans leur conteneur. Les éléments techniques restent limités aux informations utiles pour le rôle.

Mesures : trois graphiques séparés, catégories autorisées seulement, sélecteur Jour/Semaine/Mois commun, vraie pagination, dates/unités/lacunes visibles. Donnée absente n'est pas zéro. Les valeurs de pression sont relatives, sans conversion en Newton ni diagnostic. Connexion `stale` = « Données anciennes », pas vert connecté. La synthèse indique si les données chargées sont incomplètes et ne présente alors aucun faux cumul.

Notifications : expliciter l'absence de configuration d'envoi sans demander automatiquement la permission OS. La montre seule n'est pas supportée par le Web Push standard de ce banc. Ne pas confondre préférences enregistrées et envoi effectif.

La recette visuelle se fait sur http://127.0.0.1:8773, base QA séparée du banc Docker principal https://localhost:8443. Les secrets QA sont dans `../application/.runtime/qa-browser/comptes_locaux.json` : les lire en mémoire uniquement pour connexion, ne jamais les imprimer ou capturer. Les scripts existants `../verification/test-application-ui.cjs` montrent le login TOTP. Conserver les sessions plutôt que multiplier les connexions (limitation 12/10 minutes). Playwright existant sous `C:/Users/lebre/.agents/skills/playwright/node_modules/playwright` ; navigateur visible. Ne rien installer.

Évaluation indépendante requise, verdict PASS/NEEDS REVISION/MAJOR REVISION dans la réponse. Déposer rapport et captures dans `../verification/`. Ne pas affirmer conformité clinique ou essais sur tous appareils physiques. L'interface est une application réelle de banc synthétique, les tâches matérielles/externe restent explicitement conditionnées.
