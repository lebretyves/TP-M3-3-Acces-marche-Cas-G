# TP M3-3 — Accès au marché — Équipe 02

Travail du module 3, cas G : souris ergonomique à batterie unique de 1 500 mAh. Version du 19 octobre 2026.

Équipe : [lebretyves](https://github.com/lebretyves), [Faucourt](https://github.com/Faucourt) et [aglnix](https://github.com/aglnix).

## Livrable à remettre

**[Ouvrir le classeur complété](analyses/m3/acces_marche_eq02.xlsx)**

Les trois onglets demandés sont renseignés :

- **Qui paie** : bénéficiaire, décideur, payeur, cinq voies comparées et vente directe B2C retenue.
- **Frise** : six jalons du cas pédagogique B, réponses Q5 à Q9, durée de 48 mois et gain de 24 mois par rapport aux 72 mois successifs.
- **Votre projet** : finalité, qualification, classe proposée, référentiels, données, risques et prochaine étape.

Les réponses Q1 à Q4 et leur contexte figurent aussi dans Lisez-moi. La question Q2 compare les versions bien-être et médicale ; la version médicale est retenue.

## Hypothèse retenue

**Hypothèse 2 : dispositif médical**, avec deux fonctions prévues : suivi des indicateurs physiologiques et de leurs tendances, et estimation personnalisée du risque de complications cardiovasculaires en lien avec le stress et la sédentarité. L’utilisateur choisit et paie le produit ; il peut choisir de partager ses résultats avec un professionnel de santé.

La classe IIa est une hypothèse argumentée du TP sous la règle 11 pour le logiciel. Elle doit être confrontée aux décisions permises et aux conséquences des erreurs ; IIb ou III peuvent s’appliquer. Le rôle du matériel reste à examiner. Aucune certification ou performance clinique n’est acquise.

R3 programme l’acquisition et l’affichage des signaux. Le score cardiovasculaire reste à développer et valider. Le choix d’utiliser une IA pour ce futur score n’est pas encore arrêté. Les 48 mois de la frise décrivent le cas B du sujet, pas un délai de commercialisation validé pour la souris.

## Sujet et exercices précédents

- [Énoncé étudiant](supports/TP_M3_3_Acces_marche_etudiant.pdf) et [modèle original](supports/TP_M3_3_Acces_marche_original.xlsx), conservés à l’identique.
- [Copie de la classification M3-1](analyses/m3/grille_classification_eq02.xlsx), issue du [dépôt M3-1](https://github.com/lebretyves/TP-M3-1-Classification-Produits).
- [Copie de l’analyse des risques M3-2](analyses/m3/analyse_risques_eq02.xlsx), issue du [dépôt M3-2](https://github.com/lebretyves/TP-M3-2-Analyse-risques-Cas-G).
- [Projet technique et configuration retenue](https://github.com/lebretyves/TP4-IoT-Autonomie/tree/cas-g-choisi/cas_g_choisi).

Les copies des exercices 1 et 2 sont placées dans le même dossier, comme demandé dans le sujet. Leurs sources et corrections restent maintenues dans leurs dépôts respectifs.

## Vérifications et reproduction

Le classeur a été relu et contrôlé : 92 réponses attendues renseignées, 31 choix de listes valides, 26 formules du modèle conservées et trois adaptations explicites. Recalcul natif dans Microsoft Excel sans erreur de formule ; classement commercial et dépendances testés par modification temporaire des entrées. Chemin critique et marges recalculés indépendamment. Mise en page inspectée.

Voir [le contrôle du classeur](analyses/m3/verification_acces_marche.json), [le rapport Excel](analyses/m3/verification_excel_natif.json) et [les empreintes des copies](sources/provenance.json). Ces contrôles ne constituent pas une validation matérielle ou clinique.

Le [générateur](sources/remplir_acces_marche.mjs) utilise Node.js et `@oai/artifact-tool`, disponible dans l’environnement Codex utilisé pour ce travail. Les dépendances locales ne sont pas versionnées. Avec cette dépendance disponible :

```powershell
node sources/remplir_acces_marche.mjs
```

La [finalité commune](sources/finalite.json) sert d’entrée. Une nouvelle génération doit être suivie d’une vérification visuelle et d’un recalcul Excel ; les rapports présents décrivent uniquement le fichier dont l’empreinte est enregistrée.
