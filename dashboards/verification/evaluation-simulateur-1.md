# Evaluation — Attempt 1

## Overall Verdict: PASS

## Overall Assessment
Le simulateur reprend clairement l’identité SKELIVIA tout en assumant une fonction différente des dashboards métier : configuration opérateur à gauche, résultats vérifiables à droite, références séparées en bas. La composition est professionnelle, lisible et cohérente aux cinq largeurs examinées; les distinctions entre aperçu, hypothèses, données enregistrées et transmission sont explicites. Quelques détails de présentation peuvent encore faciliter l’inspection de longues listes et de la provenance.

## Scores
| Criterion | Score | Status | Weight | Notes |
|-----------|-------|--------|--------|-------|
| Design Quality | 2/3 | PASS | HIGH | Identité marine/turquoise et titre Orbitron clairement assumés, espaces et hiérarchie cohérents, configuration/résultats/références bien distingués. |
| Originality | 2/3 | PASS | HIGH | Composition spécifique au travail de banc, étapes numérotées discrètes, cible fixe latérale et preuves repliables; une adaptation réelle à SKELIVIA plutôt qu’un tableau de bord générique. |
| Craft | 2/3 | PASS | MEDIUM | Corps courant et labels à 16 px, métadonnées secondaires à 14 px, commandes mesurées au moins 44 px, focus visible et aucun débordement global dans les 20 états capturés. |
| Functionality | 2/3 | PASS | MEDIUM | Catalogue réel, changement de source/scénario, aperçu, hypothèses et provenance fonctionnent sans erreur JavaScript. Les longues listes sont défilantes mais leur affordance peut être plus explicite. |

## What's Working Well
- Le logo original et le titre incliné composent une signature immédiate; la grande zone de titre reste lisible sans mots coupés à 320 px.
- Les deux étapes Configurer et Exécution organisent le travail. La tablette utilise intelligemment une rangée de configuration avec actions latérales; le téléphone réorganise tout verticalement.
- Les boutons d’aperçu, de transmission et d’ouverture du dashboard sont distincts. Les neuf actions déclenchées pendant cette revue sont exclusivement des POST `/api/preview`, sans émission.
- Les messages « Aperçu · sans émission » et « aucune fenêtre envoyée au broker » encadrent les résultats. La cible et le détail réseau ne prétendent pas que la réception MQTT prouve une écriture en base.
- La durée, les unités du mode manuel et les ADC fictifs sont explicitement libellés. Les champs de contact et d’appuis n’apparaissent que dans le contexte approprié.
- En phyphox sans hypothèses, le tableau montre des tirets et le statut Invalide au lieu de faux zéros; les épisodes gyro restent consultables dans la synthèse et la liste d’événements. Avec hypothèses, leur nature synthétique reste indiquée dans la configuration et la provenance.
- Les références balance affichent leurs grammes séparément et expliquent qu’il ne s’agit ni d’une conversion ADC ni d’une calibration FSR.
- Le scénario Coupure réseau explique correctement l’absence de transmission pendant toute l’exécution et le lancement ultérieur d’un scénario Normal. La différence entre coupure courte et seuil de données anciennes de 120 secondes est visible.
- Un changement de configuration conserve l’ancien aperçu tout en affichant explicitement qu’il faut recalculer : état utile et honnête.
- Les tableaux défilants ont une indication textuelle et restent contenus. Les références dépliées restent lisibles à 320 px, y compris les noms de fichiers longs.
- Tab passe du bouton Aperçu au bouton Envoyer avec un contour turquoise visible. Les labels sont associés aux champs et les disclosures natifs sont accessibles au clavier.

## Issues Found
### Issue 1: Défilement des événements peu annoncé
- **What**: Le résumé peut annoncer 12 épisodes alors que seulement quatre ou cinq événements sont immédiatement visibles dans la zone de hauteur limitée. La liste est bien défilante, mais son titre ne donne pas le nombre et aucune indication de défilement comparable à celle du tableau n’est affichée.
- **Where**: « Événements de démonstration », notamment `normal-preview-390.png` et `normal-preview-1440.png`.
- **Why it matters**: Un opérateur peut croire que les événements visibles représentent toute la liste, surtout lorsque la barre de défilement est discrète.
- **Suggested fix**: Afficher le nombre total et une aide concise « Faites défiler les événements » lorsque la liste déborde; conserver son accès clavier. Non bloquant.

### Issue 2: Provenance technique partiellement non traduite
- **What**: `native_timestamp_replay`, `native gyro timestamps; linear accel interpolation…` et les règles du moteur sont affichés tels quels en anglais sous des labels français.
- **Where**: Provenance de l’exécution phyphox, `provenance-references-1440.png` et `provenance-references-320.png`.
- **Why it matters**: Ces informations sont utiles à un opérateur technique, mais une phrase française explicative rendrait les limites plus faciles à comprendre sans connaître les identifiants du moteur.
- **Suggested fix**: Ajouter un libellé français lisible tout en gardant la valeur technique originale dans une sous-section de détail. Non bloquant.

## Priority Fixes for Next Attempt
Aucun blocage ni nouvelle tentative obligatoire. Pour une finition ultérieure : rendre le défilement et le nombre des événements plus visibles, puis améliorer les libellés de provenance.

## Should the next attempt REFINE or PIVOT?
REFINE si une nouvelle itération est entreprise. Le système visuel et la structure répondent au besoin; aucun changement de direction n’est nécessaire.

## Coverage and limits
Application réelle `http://127.0.0.1:8774`, navigateur Chromium visible, sans authentification ni installation. Vingt captures de page aux largeurs 320/375/390/768/1440, avec parcours complet de la page. Aperçus Wokwi normal, manuel, intensif, appuis élevés, immobile, invalide et coupure réseau. Rejeu phyphox sur la session Usage avec et sans hypothèses; les trois sessions du catalogue sont présentes. Provenance, balance et limites des sources dépliées; clavier vérifié sur les actions.

Aucun débordement global ni erreur JavaScript constaté. Aucun champ, bouton ou summary mesuré sous 44 px hors case à cocher, dont le label englobant fournit la cible. Les données et mesures d’inspection sont dans `simulator-eval-1/observations.json`.

Conformément au mandat, aucun démarrage, pause, reprise, arrêt, envoi MQTT ou modification des dashboards n’a été exécuté. Cette revue ne certifie donc pas la transmission en direct ni les états d’exécution active. La correction de portée fournie avec le mandat — coupure pendant toute l’exécution puis arrêt/Normal pour reprendre — prime sur la phrase devenue obsolète 10–25 secondes dans le brief. Il s’agit d’une validation de rendu et d’usage sur banc, pas d’une preuve clinique.

Captures : `dashboards/verification/simulator-eval-1/`.
