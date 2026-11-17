# Bilan du scénario — contrôles de l’interface

Ajout ciblé sur l’interface existante : section visible « Bilan du scénario », cinq compteurs, tableau « Attendu / observé » et raccourcis. Aucun changement des courbes, des actions, de l’authentification ou du moteur.

16 cas d’interface et 8 assertions du calcul pur réussis avec réponses API contrôlées :

- État initial : tirets, sans faux zéros.
- Aperçu : prévisions dans le tableau, observations « Non exécuté » et compteurs vides.
- Démarrage : zéros observés lorsque les listes sont réellement vides.
- Exécution partielle avec fenêtres valides, invalides et calibration requise.
- Transmission acceptée, absence de transmission locale/réseau et réception inconnue comptées séparément.
- Épisodes de mouvement comptés dans les événements déjà détectés ; événements futurs et prévisions exclus.
- Pause stable, fin complète, arrêt partiel et échec de transmission distincts.
- Modes local et coupure réseau : zéro transmission prévue.
- Informations absentes : inconnues conservées, sans qualité ou résultat inventé.
- Nouveau choix : bilan précédent effacé.
- Raccourcis accessibles au clavier : focus de la section et ouverture des options.

Captures complètes de la section à 1440, 768, 390 et 320 pixels, sans débordement du tableau ni de la page. Pour conserver le titre sur les captures étroites, leur hauteur de viewport est de 2000 pixels. Le contenu est capturé par le sélecteur `#scenario-bilan`.

Résultat structuré : `results.json`. Captures : `bilan-1440.png`, `bilan-768.png`, `bilan-390.png`, `bilan-320.png`.

Syntaxe vérifiée par `node --check` pour `stats.js` et `app.js`. Aucune erreur JavaScript observée. Aucun scénario réel, compte ou envoi MQTT n’a été déclenché par ces essais ; la recette réelle est effectuée séparément par l’agent principal.
