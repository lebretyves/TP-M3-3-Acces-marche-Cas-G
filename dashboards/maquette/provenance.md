# Provenance de la maquette SKELIVIA

## Projet Atelier de l'utilisateur

Source consultée : `E:/Archive_Web_design/studio-createur-sites`, dépôt `lebretyves/atelier_Web`, commit `227ccc87fb4b7a561a1209ac06ad63ab795c933f`.

Réemploi autorisé par l'utilisateur. Les adaptations sont intégrées dans `assets/app.js`, avec commentaires de provenance ; aucun fichier source Atelier n'est modifié et aucune de ses dépendances applicatives n'est importée.

| Source Atelier | Adaptation dans SKELIVIA |
|---|---|
| `public/ui-app-shell.js` — `mountAppShell`, navigation responsive | État du menu mobile, `aria-expanded`, écoute du breakpoint, Échap et restitution du focus. Adaptation avec `inert` pour la navigation masquée et confinement du focus quand le panneau est ouvert. |
| `public/universal-interactions.js` — `openDialog`, `closeDialog`, `restoreDialogFocus` | Boîte de dialogue native, mémorisation du déclencheur, fermeture et retour du focus. Les dialogues de SKELIVIA sont peuplés par les formulaires du scénario, sans dispatcher ou fonctions génériques de l'éditeur. |
| `public/universal-interactions.js` — runtime d'onglets | `aria-selected`, index de tabulation, navigation flèches/Home/End et focus dans la fiche soignant. |
| `public/advanced-block-runtime.js` — bloc `data-table` | Recherche insensible aux accents et mise à jour de l'état vide dans la liste patients, tri et indication `aria-sort`. La pagination complète n'est pas reprise pour quatre lignes. |
| `public/form-flow.js` — parcours à étapes et validation | Principe de progression et validation des étapes adapté à un parcours de calibration fictif de trois étapes. Aucun appel `fetch` ou soumission réseau du runtime n'est repris. |

Le CSS SKELIVIA est écrit pour la palette et les dispositions validées. Il conserve les principes de l'application Atelier consultée : bordures fines, angles mesurés et navigation utilitaire. Aucune licence générale du code propre à Atelier n'a été identifiée dans les sources suivies consultées ; il n'est pas présenté comme du code tiers MIT.

L'entrée NudaUI Dot Badge avait été repérée dans le catalogue, mais son code n'est pas copié : les marqueurs de statut de cette maquette sont du HTML/CSS simple écrit ici.

## Logo original et typographie — itération 2

Le fichier exact joint par l'utilisateur est intégré à partir de `assets/skelivia-logo-original.png` : 2172 × 724 pixels, RGBA, SHA256 `625ad02c9ec7488c28a75cd6af30ed02f0e21d22ac45a3675876255990ba674a`. Le PNG est intact : aucun recadrage, filtre, changement de couleur ou étirement. Il s'affiche proportionnellement sur une surface blanche afin de préserver le contraste de ses lettres bleues.

La police des grands titres est maintenant **Orbitron**, fichier local `assets/Orbitron.ttf`, fourni par l'agent principal depuis la source officielle Google Fonts. Licence SIL Open Font License 1.1 conservée dans `assets/Orbitron-OFL.txt`.

- Métadonnées : https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/METADATA.pb
- Licence : https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/OFL.txt

La graisse 900 et une inclinaison synthétique CSS de 12 degrés approchent le caractère large et anguleux demandé. Ce n'est pas une identification de la police exacte du logo ni une italique native d'Orbitron. Le chargement est local avec `font-display: swap`. Les textes courants restent en `Segoe UI, system-ui, sans-serif`, sans redistribution de police système. Saira, conservée comme trace de l'itération 1 avec sa notice, n'est plus chargée par la page.

## Autres éléments

- Petits pictogrammes SVG de schématisation écrits pour la maquette ; aucune illustration générée ni bibliothèque d'icônes téléchargée.
- Données, identifiants et textes de scénario fictifs, sans lecture de données sensibles de l'utilisateur.
- Aucun CDN, image externe, analytics, assistant IA, accès à un service médical ou appel réseau tiers depuis la page.
