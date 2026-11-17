# SKELIVIA — Dashboards

Point d'entrée du travail sur les quatre espaces métier (utilisateur, soignant, employeur/prévention, support) et l'administration sécurité séparée.

## Application intégrée

Le [simulateur d'utilisation](simulateur/README.md) rejoue les sept modes Wokwi et trois acquisitions phyphox. Ouvrir [Ouvrir simulateur SKELIVIA.cmd](Ouvrir%20simulateur%20SKELIVIA.cmd) pour calculer un aperçu ou transmettre des fenêtres synthétiques au dashboard d'Alice via MQTT privé.

L'[application réelle de banc SKELIVIA](application/README.md) est maintenant séparée de la maquette : API persistante, PostgreSQL privé, Keycloak avec MFA, broker mTLS et cinq espaces avec leurs droits serveur. Démarrer via [Ouvrir application SKELIVIA.cmd](Ouvrir%20application%20SKELIVIA.cmd), puis `https://localhost:8443` sur ce PC. Le certificat local, les accès de recette et les prérequis externes sont expliqués dans son README.

Le [PDF retrouvé et sa traçabilité](application/ARCHITECTURE_ET_RECETTE.md) guident cette réalisation. Les données restent fictives ; les intégrations matérielles, cliniques et d'hébergement ne sont pas prétendues activées. Les sections suivantes conservent l'historique de la maquette visuelle.

## Dossiers

- [Conception et choix validés](conception/Propositions_personas_donnees_securite.md) : 71 décisions positives, 16 refus, identité visuelle et dispositions des accueils.
- [Brief de réalisation de la maquette](conception/brief-maquette.md).
- [Maquette navigable](maquette/index.html) : cinq espaces avec données fictives, prêts pour la revue du rendu.
- `maquette/assets/` : styles, scripts et police locale avec sa licence.
- `verification/` : serveur local de présentation, contrôles et captures.

La maquette est isolée de l'application métier. Les changements d'espace servent à la revue et ne représentent pas une possibilité de changer ses droits dans le produit. Les actions sont simulées ; aucune donnée de santé réelle ni notification externe n'est traitée.

Pour ouvrir la maquette, double-cliquer sur [Ouvrir SKELIVIA.cmd](Ouvrir%20SKELIVIA.cmd). Le lanceur réutilise le serveur local existant ou le démarre, puis ouvre le navigateur.

Le serveur local de présentation est accessible à [http://127.0.0.1:8771](http://127.0.0.1:8771) lorsqu'il est lancé. Pour le démarrer manuellement :

```powershell
node "E:\TP M3 3\dashboards\verification\serveur-local.cjs"
```

## Vérifications de la maquette

Contrôles effectués le 14 novembre 2026 :

- [Navigation et formats](verification/captures/verification-navigation.json) : 56 vérifications, cinq espaces, largeurs 320, 360, 390, 768, 1024 et 1440 pixels. Aucun débordement horizontal de page, erreur JavaScript ou ressource en échec détecté.
- [Parcours principaux](verification/captures/verification-parcours.json) : 18 vérifications comprenant périodes, partage/révocation, calibration simulée, dossier soignant et limites, avancement employeur, clôture de ticket conditionnée, qualification d'incident et préférences ; menus et notifications des cinq espaces dans WebKit avec profils iPhone/iPad.
- [Supports et orientations](verification/captures/verification-supports.json) : 25 contrôles complémentaires sur profils Android portrait/paysage, iPhone paysage, tablette paysage et bureau WebKit.
- [Cohérence entre espaces](verification/captures/verification-coherence.json) : sept scénarios réussis couvrant la révocation et le filtrage des partages, les versions par patient, les interventions et réponses support, les incidents, les certificats et sessions, les comptes neufs et le suivi des suppressions. Aucune erreur JavaScript détectée.
- [Régressions ciblées](verification/test-implementation-regressions.cjs) : assistance soignant sans appareil patient, réactivation d'un compte neuf, diagnostic fermé et calibration après remplacement vérifiés.
- [Revue visuelle indépendante](verification/evaluation-1.md) : première maquette acceptée pour revue, avec corrections de lisibilité mobile/tablette intégrées.
- [Revue visuelle finale](verification/evaluation-final-1.md) : PASS sur les nouvelles sous-vues à 1440, 390 et 320 pixels ; 36 captures ciblées, aucun débordement global ni erreur JavaScript. Aucun défaut bloquant relevé.
- Aperçus : [utilisateur sur ordinateur](verification/captures/user-1440.png), [utilisateur sur téléphone](verification/captures/user-390.png), [tablette](verification/captures/user-768.png).

Ces vérifications utilisent des moteurs et profils émulés sur ce poste. Elles ne constituent pas des essais sur chaque iPhone, appareil Android, tablette ou Mac physique. Les notifications téléphone/montre sont représentées par leurs réglages ; aucun envoi réel n'est réalisé.

## Validation visuelle des accueils

- **Utilisateur :** rendu général accepté, puis logo original et grands titres corrigés explicitement validés.
- **Soignant :** rendu présenté accepté le 14 novembre 2026 : liste des patients, accès aux bilans autorisés et rappels de réexamen à droite.
- **Employeur/prévention :** premier rendu refusé avec demande de colorer les chiffres des compteurs. Correction réalisée : à traiter en orange/ambre, en cours en bleu, réalisée en vert, bloquée en rouge ; libellés et disposition conservés. Vérification à 1440 et 390 pixels et actualisation des compteurs après changement de statut réussies. [Aperçu corrigé](verification/captures/employer-colors-1440.png), [revue ciblée passée](verification/evaluation-3.md).
- **Finalisation :** l'utilisateur a demandé de terminer l'ensemble et de réserver ses éventuelles corrections à plus tard. Les cinq espaces et leurs parcours simulés sont finalisés sans nouvelle question de validation. Cette consigne ne constitue pas une approbation visuelle détaillée des écrans non examinés.

## Identité visuelle corrigée

Le [PNG original SKELIVIA](maquette/assets/skelivia-logo-original.png) fourni par l'utilisateur est intégré intact. Les titres utilisent Orbitron, avec une inclinaison visuelle, pour se rapprocher des formes du logo ; le nom exact de la police du logo n'est pas établi. Les sources et licences sont détaillées dans la [provenance](maquette/provenance.md).

La [revue visuelle de cette correction](verification/evaluation-2.md) conclut PASS : logo original inchangé, proportions conservées, titres inclinés et lisibles sur les formats examinés. Les 56 contrôles de navigation/formats ont également été rejoués sans échec. Aperçus corrigés : [ordinateur](verification/captures/brand-1440.png), [téléphone](verification/captures/brand-390.png), [logo dans le menu mobile](verification/captures/brand-menu-390.png). Le 14 novembre 2026, l'utilisateur a explicitement validé le logo original intégré et le nouveau style large, anguleux et incliné des grands titres. Cette identité est retenue pour les cinq espaces finalisés ; les éventuelles corrections seront faites sur demande.

L'[architecture de référence](../outputs/P1_ARCHITECTURE_SECURISEE_20261113/Proposition_architecture_securisee_personas_P2.pdf) et les sources techniques P1/P2 restent à leurs emplacements de référence. Ce dossier centralise la conception et les livrables des dashboards sans dupliquer ces sources.
