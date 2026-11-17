# SKELIVIA — maquette navigable

Maquette interactive des cinq espaces, préparée le 14 novembre 2026 à partir des décisions consignées dans `../conception/Propositions_personas_donnees_securite.md`. L'utilisateur a demandé de terminer l'ensemble et réserver ses éventuelles corrections visuelles à plus tard.

## Ouvrir

Sous Windows, double-cliquer sur `../Ouvrir SKELIVIA.cmd` (Node.js requis). Le serveur sert uniquement ce dossier à l'adresse `http://127.0.0.1:8771`, sur ce PC. Pour le démarrer depuis un terminal, utiliser `node verification/serveur-local.cjs` depuis le dossier `dashboards`. Les fichiers peuvent également être ouverts depuis `index.html` ; la version servie localement est recommandée pour les vérifications navigateur.

Le sélecteur « Examiner l'espace » dans le bandeau de présentation permet de parcourir les cinq personas. Il est réservé à la maquette : ce n'est pas un mécanisme produit pour changer de rôle ou d'autorisation.

## Parcours simulés

- Utilisateur : accueil, mesures Jour/Semaine/Mois, conseils et bilan, partage à portée/durée choisies et révocation, calibration guidée, maintenance, tickets techniques, sessions, notifications et préférences.
- Soignant : patients autorisés, fermeture après révocation/expiration, filtrage par dates et catégories, dossier avec onglets clavier, comparaison de deux plages disponibles, conseils et bilans séparés par patient avec leurs versions, recommandations organisationnelles, rappels personnels et assistance. Aucun export des mesures soignant.
- Employeur/prévention : compteurs par statut, modification d'avancement, historique et récapitulatif téléchargeable sans contenu médical. Aucun champ de responsable, échéance ou motif de blocage.
- Support : tickets attribués, panneau de détail, réponses, vérifications avant clôture, calibration, mise à jour approuvée simulée, remplacement d'appareil, historique technique et signalement de sécurité.
- Administration : qualification des alertes et dossiers d'incident jusqu'à la clôture vérifiée, décisions de correctifs, comptes et rôles, sessions ciblées, certificats avec nouvelles échéances, journal d'actions, état des sauvegardes, contrôle des accès expirés et suivi d'une suppression fictive.

Les actions conservent seulement un état de présentation en mémoire. Recharger la page restaure les exemples. Les téléchargements sont de simples fichiers texte contenant des données explicitement fictives. Aucun appel API, aucune collecte matérielle, aucune modification de compte, d'accès ou de certificat réel, aucun envoi de notification ni déploiement n'est effectué.

## Affichage et appareils

Interface web responsive destinée aux navigateurs sur iPhone, Android, tablettes, PC et Mac : menu repliable, détail support dédié sur petit écran, tableaux avec défilement propre, navigation clavier, contrôles tactiles et champs mobiles à 16 pixels pour éviter le zoom de saisie courant sur Safari. Portrait et paysage sont pris en compte par des règles de largeur, pas par une détection de marque.

Cette cible responsive ne constitue pas une certification de chaque appareil ou version de navigateur. Les vérifications automatisées et captures de la revue sont conservées dans `../verification`. Il faut distinguer émulation de dimensions, tests sur moteurs installés et essais sur appareils réels. Aucun essai matériel iPhone/Android/Mac n'est revendiqué par ce document.

Ce n'est pas une application native, une PWA installée ou une intégration montre. Les options téléphone/montre représentent les préférences validées à concevoir ; aucun push, vibration ou synchronisation n'est implémenté.

## Limites de la maquette

- Les graphes utilisent un jeu synthétique déterministe et des agrégats de présentation ; ils ne valident pas les calculs du futur pipeline. Les trous ne sont pas interpolés et la calibration reste visible.
- La comparaison propose les plages disponibles du jeu fictif, filtrées selon le partage actif. Un changement de durée est signalé ; aucune évolution de santé n'est déduite.
- Les fenêtres de certificat, correctif et restauration illustrent les décisions à prendre, sans exécution de commande système.
- La preuve d'expiration, les résultats de restauration et la qualité des capteurs sont des exemples, pas des vérifications du service existant.
- Incidents, versions des documents, partages, tickets et notifications sont reliés dans l'état en mémoire. La persistance, l'authentification et l'application des habilitations doivent être intégrées côté serveur suivant l'architecture de référence.
- Les conseils et bilans sont séparés par patient fictif ; seul le patient 01 correspond à l'espace utilisateur de démonstration. Les contrôles d'affichage de ce HTML ne sont pas une protection d'accès réelle : tous ses exemples sont envoyés au navigateur.
- Les dates et heures du scénario sont figées au 14 novembre 2026. Les diagnostics actifs, expirés et révoqués sont des cas de démonstration ; ils ne dépendent pas de l'horloge réelle.
- Le logo original fourni par l'utilisateur est intégré sans retouche. Les grands titres utilisent Orbitron en graisse 900 et une inclinaison de 12 degrés pour approcher son lettrage anguleux et large. La police exacte du logo n'est pas identifiée ; Orbitron est une approximation de style validée par l'utilisateur.

Les décisions refusées ne sont pas réintroduites par le prototype. L'application FastAPI et les sources Atelier n'ont pas été modifiées.
