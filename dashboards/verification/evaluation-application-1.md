# Evaluation — Attempt 1

## Overall Verdict: MAJOR REVISION

## Overall Assessment
La direction SKELIVIA est cohérente et mérite d’être conservée : logo original, titres Orbitron inclinés, navigation marine et accents turquoise donnent une identité reconnaissable. Les cinq structures métier sont bien différenciées et les compositions se réorganisent sans débordement global. La livraison reste cependant prématurée : la lisibilité de nombreux textes courants, les petites cibles d’action et la navigation clavier du menu mobile présentent des défauts systématiques, particulièrement inadaptés à un outil de suivi ergonomique.

## Scores
| Criterion | Score | Status | Weight | Notes |
|-----------|-------|--------|--------|-------|
| Design Quality | 2/3 | PASS | HIGH | Palette cohérente, logo intact, titres distinctifs, structure claire selon le rôle. Hiérarchie visuelle des sections maîtrisée. |
| Originality | 2/3 | PASS | HIGH | Identité SKELIVIA visible, compteurs employeur colorés et explicitement libellés, compositions spécifiques soignant/support/sécurité. |
| Craft | 0/3 | FAIL | MEDIUM | Plusieurs défauts techniques fondamentaux et systématiques : textes courants de 11,25–12 px au lieu des 16 px demandés, commandes mobiles de 26,9–31 px de haut, gestion de focus mobile qui produit une exception. Le responsive spatial est solide, mais ne compense pas ces défauts de lisibilité et d’accès. |
| Functionality | 1/3 | PASS | MEDIUM | Navigation et formulaires utilisables au pointeur, périodes réelles et messages d’indisponibilité explicites. Le clavier mobile n’est pas fiable; sous-vue patient et pagination complète non vérifiables avec les données présentes. |

Le verdict MAJOR REVISION découle mécaniquement du barème : tout critère à 0 déclenche ce verdict. Il ne signifie pas qu’il faille remplacer la direction esthétique.

## What's Working Well
- Logo local original bien préservé; titres lisibles aux largeurs examinées, sans découpage de mot observé sur les pages capturées.
- Navigation marine, repère turquoise de page active, boutons primaires bleus et surfaces sobres composent un langage constant.
- Utilisateur : état souris en tête, trois catégories de graphiques distinctes puis conseils/bilan. Valeurs relatives, unités et dates visibles; mesure non exploitable représentée comme lacune dans le graphe.
- Soignant : patients suivis avec état d’accès et colonne de rappels. Le dossier fermé ne révèle aucune mesure.
- Employeur : quatre compteurs ambre/bleu/vert/rouge avec texte, tableau de recommandations organisationnelles.
- Support : liste/détail en bureau et vue dédiée du ticket sur téléphone, retour à la liste présent.
- Sécurité : alertes prioritaires, correctifs puis protections; formulaires expliquent les validations et preuves nécessaires.
- Paramètres utilisateur : distinction claire entre préférences enregistrées et envoi non configuré; limites de la montre explicitement expliquées; aucune demande automatique de permission OS observée.
- Aucun débordement horizontal global dans les 72 états de page mesurés. Les tableaux mobiles disposent d’un conteneur défilant et d’une indication de défilement.
- Les formulaires à 320 px restent dans la largeur utile et montrent un focus visuel turquoise clair.

## Issues Found
### Issue 1: Texte courant trop petit dans toute l’application
- **What**: Base de 15 px et nombreuses réductions en rem. Sur l’accueil utilisateur à 390 px, sous-titre mesuré à 11,85 px, descriptions de sections à 11,25 px, conseils et libellés de graphiques à 12 px. Les textes de tableaux, statut et aide sont également très petits. L’option « Agrandir les textes » ne remplace pas une taille par défaut correcte.
- **Where**: `app/static/app.css` : `.page-subtitle`, `.section-heading p`, `.advice p`, `.data-table`, `.chart-label`, `.field label`, `.help-text`, `.notice`, légendes et textes explicatifs. Captures `user-home-390.png`, `user-settings-390.png`, `employer-home-1440.png`.
- **Why it matters**: Le brief demande 16 px pour le texte courant. Les utilisateurs doivent lire des consignes, états et conditions importantes dans une taille bien inférieure; l’espace disponible en bureau est pourtant généreux.
- **Suggested fix**: Passer le corps et les textes de contenu/commande à 16 px minimum; réserver 14 px aux métadonnées secondaires. Reprendre explicitement les petites règles rem héritées. Revoir ensuite retours à la ligne et hauteur des lignes des tableaux aux quatre largeurs.

### Issue 2: Navigation clavier du menu mobile cassée
- **What**: Ouvrir le menu puis appuyer sur Tab produit `focusables.at is not a function`, constaté pour chacun des cinq rôles. Le gestionnaire récupère un élément via `$` puis le traite comme une liste.
- **Where**: Gestionnaire `keydown` de `app/static/app.js`; preuve répétée dans `application-eval/observations.json`, tableaux `errors` des cinq rôles.
- **Why it matters**: Le confinement du focus prévu pour le panneau modal ne fonctionne pas. Les parcours clavier et technologies d’assistance ne sont pas suffisamment fiables.
- **Suggested fix**: Utiliser `$$` pour sélectionner tous les éléments de focus, vérifier une liste non vide, puis tester Tab/Shift+Tab sur premier/dernier élément et Escape avec restauration du focus au bouton Menu.

### Issue 3: Cibles d’action mobiles trop petites
- **What**: Boutons Jour/Semaine/Mois mesurés à 26,875 px de haut, « Vérifier la souris » à environ 31 px. Plusieurs actions de support/sécurité héritent de `.small` à 31 px; autres boutons à 38 px.
- **Where**: `.period-switch button`, `.button`, `.small`, `.status-strip .button`, actions de ticket. Captures `user-home-390.png`, `user-home-320.png`, `support-ticket-detail-390.png`.
- **Why it matters**: Les commandes fréquentes demandent trop de précision tactile. Le problème concerne plusieurs composants partagés.
- **Suggested fix**: Minimum 44 × 44 px sur les commandes tactiles, en tenant compte des règles spécifiques et de la media query coarse; conserver un espacement utile entre commandes voisines.

### Issue 4: Retour du ticket collé au statut
- **What**: « ← Mes tickets » et la pastille « En cours » se touchent visuellement.
- **Where**: Détail support mobile, `support-ticket-detail-390.png`.
- **Why it matters**: Le lien de navigation et l’état du ticket paraissent former un seul libellé.
- **Suggested fix**: Disposer le retour sur une ligne dédiée ou ajouter un gap explicite dans une rangée structurée.

## Priority Fixes for Next Attempt
1. Corriger le gestionnaire clavier du menu et vérifier un cycle complet de focus sur les cinq rôles.
2. Restaurer les tailles de lecture demandées dans les composants partagés, puis contrôler tous les retours de ligne à 320/390/768/1440 px.
3. Porter les cibles mobiles à 44 px et séparer retour/statut du ticket.

## Should the next attempt REFINE or PIVOT?
REFINE. L’identité, les structures métier et le comportement de mise en page sont solides; les défauts se concentrent dans les styles partagés et un gestionnaire clavier. Conserver le logo, la palette, la composition et les titres; augmenter la lisibilité et la robustesse des interactions.

## Coverage and limits
Application réelle à `http://127.0.0.1:8773`, FastAPI et sessions des cinq rôles. Toutes les rubriques de navigation ont été parcourues et capturées à 1440 et 390 px; accueils également à 320/375/768 px. Formulaires de ticket, rappel et création de compte inspectés à 320/390 px sans soumission; notifications de chaque rôle ouvertes; détail support mobile ouvert; périodes Jour/Semaine/Mois manipulées. Captures prises après stabilisation des transitions CSS.

Le partage Alice→Lina était fermé, donc le dossier patient ouvert n’a pas été inspecté. Le jeu ne comporte que deux mesures : la pagination et le cas de synthèse incomplète ne sont pas validés visuellement par cette session. Les états inconnus du dispositif ne permettent pas de juger le rendu `stale` en situation. Aucun état métier, préférence, partage ou ticket n’a été modifié; seuls les événements ordinaires de connexion/lecture sont générés. Aucun secret ni écran de connexion n’a été capturé. Cette recette est une revue de rendu et d’usage sur banc synthétique, pas une conformité clinique ou un essai exhaustif d’appareils physiques.

Captures et mesures : `dashboards/verification/application-eval/` (72 états de page plus menus, notifications et formulaires). Données d’observation : `application-eval/observations.json`.
