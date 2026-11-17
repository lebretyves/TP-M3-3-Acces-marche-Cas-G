# Souris dynamique et repères — recette d’interface

20 cas vérifiés par Playwright avec réponses API contrôlées. Aucune simulation réelle, session métier ou émission MQTT déclenchée par ces tests.

- Quatre capteurs distincts dans le SVG : pouce, paume, mouvement et **contact**.
- Navigation clavier et sélection du contact : nom, état, valeur et explication du modèle AT42QT1011.
- États fournis par le serveur : activité verte, repos bleu, appui élevé orange, défaut rouge avec symbole « ! », information inconnue grise et hachurée.
- Jauges et compteurs issus des valeurs fournies ; aucune horloge de capteur calculée côté interface.
- Rappel de pause visible uniquement lorsque le drapeau du point affiché est vrai.
- Quatre pannes ciblées : seul le capteur choisi devient rouge.
- Rejeu phyphox incomplet et ancien contrat : une valeur absente reste inconnue, sans panne inventée.
- Mode local et coupure de scénario distincts dans la liaison souris / service.
- Frise : pas de point futur pendant une exécution ; clic sur un événement sans modifier le temps.
- Aperçu explicitement prévu, sans animation ; animations également arrêtées en pause et après arrêt.
- Préférence de réduction des animations respectée.
- Sélecteur de panne envoyé pour le scénario invalide ; valeur `all` envoyée hors de ce scénario.
- Bilan existant conservé.
- Aucun débordement à 1440, 768, 390 et 320 pixels, aucune erreur JavaScript.

Preuve structurée : `results.json`. Captures : `mouse-active-*.png`, `mouse-high.png`, `mouse-contact-fault-320.png`, `timeline-intensive-320.png`, `timeline-fault-320.png`.

La zone contact est dessinée dans le SVG, avec un bouton clavier/tap, un état textuel et son symbole de défaut. Les positions sont schématiques et ne prétendent pas valider un placement physique. Les compteurs reproduisent les règles du démonstrateur, pas un temps de travail.

Les recettes réelles et l’évaluation indépendante sont menées séparément par l’agent principal.
