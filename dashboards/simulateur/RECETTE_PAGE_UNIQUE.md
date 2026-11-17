# Simulateur sur une page — 16 novembre 2026

Adresse principale : **https://localhost:8443/simulateur/**. L'ancien accueil HTTP local redirige vers cette adresse. Le dossier du simulateur et le transport privé existants sont conservés.

## Parcours simplifié

Six scénarios disposent d'un bouton et d'une durée prédéfinie. **Lancer**, **Pause**, **Reprendre** et **Arrêter** restent sur la page. La souris et les courbes d'appuis, mouvement et contact utilisent les échantillons du moteur. Le graphique en cours ne présente aucun point situé après le temps de lecture atteint ; les valeurs absentes restent absentes. Le temps de pause n'est pas ajouté au contact. L'aperçu complet est explicitement distinct d'une exécution.

L'onglet Actions contient les formulaires des personas dans une iframe de même origine. Le compte sélectionné, la session, le CSRF et les droits métier sont revérifiés. Seule cette page de formulaire accepte l'encadrement de même origine ; les autres écrans conservent leur protection. Le retour OIDC `/simulateur/` est lié au state d'authentification et soumis à une liste de destinations fermée. Aucun accès SQL ou compte privilégié n'est ajouté au serveur du simulateur.

Le montage Wokwi original se charge à la demande dans un autre onglet de la même page. Son iframe externe utilise une sandbox ; aucune donnée du compte n'y est envoyée par notre code. Le montage reste indépendant des courbes et du transport locaux. Son affichage a été vérifié, sans lancement de simulation, modification du projet ni envoi sur son broker historique.

## Preuves

- **94 tests du simulateur réussis**, sans test ignoré : [JUnit](../verification/simulator-simple-tests.xml).
- Vérification complémentaire après correction du sous-échantillonnage : **six contrôles de courbes réussis**, dont une lacune située entre deux points conservés qui doit toujours interrompre le tracé. [JUnit complémentaire](../verification/simulator-graph-gap-tests.xml).
- **157 tests applicatifs réussis**, cinq tests réservés à une infrastructure de recette dédiée non exécutés dans ce lot : [JUnit](../verification/application-simple-tests.xml).
- Contrôle réel du proxy : `nginx -t` réussi. Le service facultatif est résolu à la demande, sans rendre son existence obligatoire au démarrage des dashboards.
- **Recette navigateur réelle PASS** : mode local sans publication, courbes alimentées, pause/reprise/arrêt, retour de connexion OIDC + MFA sur le simulateur, action autorisée dans la page, mauvais persona refusé, aucune nouvelle fenêtre, affichage sans débordement à 320/390/768/1440 pixels. [Résultats](../verification/simulator-simple-live/results.json).
- **Appuis élevés 10 secondes** : deux fenêtres reçues en base, une notification d'appui. **Intensif 30 secondes** : six fenêtres, une notification de pause. Les notifications sont reliées à l'exécution et à la séquence ; la page affiche leur réception confirmée. [Preuve PostgreSQL en lecture seule](../verification/simulator-simple-live/database-proof.json).
- **17 contrôles UI avec réponses contrôlées réussis** : invalidité, période sans données, mode local, erreurs, champs, formulaires intégrés et limites de rôle. [Résultats](../verification/simulator-simple-ui/results.json).
- **Évaluation visuelle indépendante PASS** : 11 contrôles, 18 captures, aucune erreur JavaScript ni fenêtre supplémentaire. [Captures](../verification/simulator-simple-eval-1/).
- Affichage du montage original, y compris avec sandbox : [preuve](../verification/wokwi-project-iframe-sandbox-probe.json).

Captures : [ordinateur](../verification/simulator-simple-live/curves-1440.png), [téléphone](../verification/simulator-simple-live/curves-390.png), [action intégrée](../verification/simulator-simple-live/inline-action-1440.png), [montage Wokwi](../verification/simulator-simple-live/wokwi-inline-1440.png).

## Complément du 17 novembre : bilan accessible

Le raccourci **Voir le bilan** près des commandes ouvre la section visible **Bilan du scénario**, avec les compteurs colorés et le tableau **Attendu / observé**. Les scénarios, courbes, actions intégrées et montage Wokwi sont conservés. Les raccourcis des options avancées et du rapport facilitent leur accès.

La recette réelle vérifie les aperçus Normal, Capteur invalide et Coupure réseau contre les prévisions retournées par l'API : aucune valeur observée n'est affichée comme exécutée. Un scénario Normal de cinq secondes en mode local donne une fenêtre valide, une fenêtre non transmise, zéro acceptation MQTT et trois épisodes de mouvement ; le tableau correspond aux fenêtres et événements effectivement retournés par le service. Les contrôles de débordement passent à 320, 390, 768 et 1 440 pixels, sans erreur JavaScript. [Résultats](../verification/simulator-bilan-live/results.json).

Seize contrôles navigateur avec réponses simulées couvrent notamment le démarrage à zéro, le bilan partiel, la pause, l'arrêt, l'invalidité, la calibration requise, les envois incertains, les données manquantes, l'exclusion des mouvements futurs et la remise à zéro lors d'un changement de scénario. Les accès directs sont aussi vérifiés au clavier. Aucun de ces contrôles ne modifie le service réel. [Résultats UI](../verification/simulator-bilan-ui/results.json).

L'évaluation indépendante conclut **PASS** après treize vérifications et neuf captures, sans erreur JavaScript ni mutation réelle. [Captures indépendantes](../verification/simulator-bilan-eval-1/). Aperçus complets du bilan : [ordinateur](../verification/simulator-bilan-ui/bilan-1440.png) et [téléphone](../verification/simulator-bilan-ui/bilan-390.png).

## Complément du 17 novembre : capteurs dynamiques

Le dessin comporte quatre zones distinctes : Pouce, Paume, Mouvement et Contact. Le capteur Contact est explicitement présent dans le SVG, accessible au clavier et au toucher. Les états sont fournis par le moteur : activité/contact vert, repos/absence bleu, appui élevé orange, panne injectée rouge et données inconnues grises. La panne ciblée se choisit directement sous les scénarios rapides. Les compteurs et la frise utilisent les données de l'exécution, sans horloge de calcul indépendante dans le navigateur.

La suite du simulateur passe **107 tests**, sans test ignoré, y compris la comparaison native des sept scénarios de référence. Les pannes ciblées sont testées séparément comme extensions locales ; les événements de défaut ne sont pas transmis comme alertes d'usage. [JUnit](../verification/simulator-visual-tests.xml).

La recette navigateur réelle confirme les quatre pannes ciblées, l'accès clavier au capteur Contact, les appuis élevés en orange et les valeurs phyphox absentes en gris. Une panne de contact de cinq secondes en mode local, avec pause/reprise, produit une fenêtre invalide sans publication MQTT. Un scénario Normal de dix secondes passe du contact présent au contact absent. Aucun échantillon ni événement futur n'est présenté en direct. Les contrôles à 320, 390, 768 et 1 440 pixels ne détectent aucun débordement ni erreur JavaScript. [Résultats](../verification/simulator-visual-live/results.json), [dessin sur ordinateur](../verification/simulator-visual-live/contact-fault-1440.png), [dessin sur téléphone](../verification/simulator-visual-live/contact-fault-390.png).

Vingt contrôles UI avec réponses simulées couvrent les couleurs, la sélection de panne, les anciens enregistrements, les compteurs, l'accès clavier, le respect du mouvement réduit, les modes local/réseau et l'exclusion des événements futurs. Un clic sur la frise ne déplace pas l'horloge. [Résultats UI](../verification/simulator-visual-ui/results.json).

Après ajustement de la géométrie SVG, le capteur Contact, son texte et son symbole de défaut sont entièrement dans le contour de la souris. Six captures et les contrôles géométriques/clavier confirment les états actif, défaut et inconnu sur ordinateur et petit écran. [Preuves de la correction](../verification/simulator-visual-ui-revision-2/). Les captures réelles ci-dessus ont été renouvelées en aperçu, sans nouvelle exécution.

L'évaluation indépendante finale conclut **PASS** : seize contrôles réussis, quinze nouvelles captures et aucune erreur JavaScript. [Captures de validation](../verification/simulator-visual-eval-2/).

## Limites conservées

Une détection locale, une réception MQTT et une notification en base sont trois états distincts. La confirmation visible provient uniquement des notifications de l'utilisateur connecté, filtrées par l'exécution. La recherche est bornée aux dernières 500 notifications sur 24 heures et signale une éventuelle troncature. Une absence de résultat n'est pas présentée comme une preuve d'absence de notification. Les préférences, le report des pauses et la limite d'une notification par minute et par type restent appliqués.

Les graphiques sont ceux du moteur local dérivé de Wokwi ou du rejeu phyphox ; les boutons de l'iframe Wokwi ne les commandent pas. Le mode local fonctionne sans publication MQTT. Les fichiers de balance ne constituent toujours pas une calibration physique FSR. Les seuils restent des seuils de démonstration. Web Push demeure désactivé sur ce banc ; aucun téléphone ni montre n'a reçu de notification pendant cette recette.
