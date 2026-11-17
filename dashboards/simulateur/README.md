# Simulateur d'utilisation SKELIVIA

Ce panneau opérateur rejoue sept modes Wokwi et trois acquisitions phyphox. Il calcule les fenêtres de mesures puis peut les transmettre en temps réel par le broker privé, avec le certificat du seul appareil fictif d'Alice. Le serveur du simulateur ne possède aucun accès à PostgreSQL ni clé privée de CA.

Ouvrir [Ouvrir simulateur SKELIVIA.cmd](../Ouvrir%20simulateur%20SKELIVIA.cmd), puis **https://localhost:8443/simulateur/**. Docker Desktop doit fonctionner. L'ancienne adresse `http://127.0.0.1:8774` redirige vers cette page. Les courbes, les événements et les formulaires d'actions sont réunis dans le simulateur.

## Utilisation

1. Cliquer sur un scénario, par exemple **Intensif**. Sa durée et son résultat attendu sont déjà renseignés.
2. Cliquer sur **Lancer**. Observer la souris, les trois graphiques (appuis, mouvements et contact) et les événements sur la même page.
3. Utiliser **Pause**, **Reprendre** ou **Arrêter**. La fenêtre incomplète est abandonnée lors de l'interruption et recommence à la reprise ; la pause ne devient pas du temps de contact.
4. Pour tester un autre persona, ouvrir l'onglet des actions et choisir son action. Son formulaire apparaît directement dans la page. Une connexion sécurisée peut être nécessaire ; elle revient au simulateur après authentification.
5. Le montage du projet est visible dans l'onglet **Wokwi**, après chargement. Il reste indépendant du moteur local : ses boutons ne commandent pas les courbes ni les dashboards.

Les réglages avancés conservent la durée (5 à 300 secondes), les trois rejeux phyphox, les réglages manuels, l'aperçu sans émission, les événements à transmettre et le rapport. Le mode local affiche les résultats sans connexion MQTT ; le mode dashboard transmet les agrégats par fenêtres de cinq secondes. Le graphique s'actualise avant la fin de chaque fenêtre, à partir des échantillons du moteur réellement atteints par l'horloge de lecture. Il ne montre pas les points futurs comme des observations. L'aperçu, lui, montre explicitement le scénario complet.

Les courbes ne transforment pas les valeurs manquantes en zéros. Le gyroscope phyphox peut rester visible lorsque les appuis et le contact ne sont pas mesurés. L'affichage est borné à 6 000 points issus du moteur, avec sous-échantillonnage des longues acquisitions.

**Voir le bilan**, près des commandes, mène directement au **Bilan du scénario**. Les compteurs indiquent les fenêtres valides, non exploitables, transmises et non transmises ; une fenêtre regroupe cinq secondes de mesures. Les transmissions dont la réception est inconnue restent séparées. Le tableau **Attendu / observé** compare le scénario complet aux fenêtres et mouvements déjà observés. En aperçu, seule la prévision est renseignée : aucune exécution n'est affirmée. Un arrêt ou une pause laisse un bilan partiel, sans conclure à un échec.

Les prévisions et observations proviennent du même moteur : ce bilan facilite la lecture du scénario, mais ne constitue pas une validation indépendante de ses calculs. Une transmission comptée signifie uniquement que le broker l'a acceptée ; la confirmation dans le dashboard reste affichée séparément dans les événements. En mode local ou en coupure réseau, aucune transmission n'est attendue.

Le mode Coupure coupe la connexion MQTT du simulateur et n'émet aucune fenêtre pendant toute la session. Pour reprendre, arrêter puis lancer Normal. Une coupure de 10 secondes ne suffit pas à franchir le seuil de fraîcheur de 120 secondes du dashboard ; choisir 125 secondes pour cet essai. Aucun changement de seuil de production n'est effectué.

## Lire le dessin de la souris

Le schéma distingue les appuis **Pouce** et **Paume**, le **Mouvement** et le capteur **Contact**. Chaque zone affiche un état : vert pour l'activité ou le contact, bleu pour le repos ou l'absence de contact, orange pour un appui élevé, rouge avec un symbole de défaut pour une panne injectée, gris pour une donnée inconnue. Les textes et symboles complètent les couleurs. Le contact représente le signal capacitif émulé du projet ; le dessin ne valide pas le placement physique sous la coque.

Choisir **Capteur invalide**, puis le capteur concerné, pour essayer une panne ciblée. Les autres canaux conservent leurs mesures locales. Le choix de panne multiple conserve le scénario original. Les hypothèses de contact et d'appuis ajoutées au rejeu phyphox restent fictives ; sans ces hypothèses, ces zones sont grises.

Les indicateurs de contact, d'immobilité et de rappel suivent les compteurs du moteur. La frise situe les événements sur la même durée que les courbes, en distinguant les injections manuelles. La liaison au service décrit le transport : une coupure réseau ne met pas les capteurs en panne. L'aperçu est un calcul préalable ; les confirmations de transmission et de notification ne sont affichées qu'après observation de leur étape respective.

## Rejeu phyphox et balance

Le rejeu conserve les timestamps natifs du gyroscope, les lacunes et la confirmation d'un épisode à sa fin. L'accéléromètre est aligné seulement lorsque deux échantillons voisins sont séparés d'au plus 0,2 seconde. Les réglages et leur port sont décrits dans [ENGINE.md](ENGINE.md).

Les acquisitions phyphox ne mesurent pas les deux FSR et le contact de la souris. Sans hypothèses explicites d'appui/contact, les fenêtres sont marquées invalides, même si les épisodes gyro calculés restent consultables dans l'aperçu. Si des hypothèses sont choisies, le résultat demeure une simulation hybride et les hypothèses figurent dans sa provenance. Il n'est pas présenté comme une acquisition simultanée de tous les capteurs.

Les six lectures ponctuelles de balance sont affichées séparément comme références exploratoires. Elles ne calibrent pas les FSR : aucune conversion grammes → ADC ou pourcentage n'est inventée. Les seuils d'appui et de rappel Wokwi sont ceux de démonstration, pas des seuils cliniques.

## Architecture et preuves

`moteur → fenêtres synthétiques → MQTT mTLS/ACL → worker applicatif → PostgreSQL → dashboard autorisé`

Chaque session possède un UUID, des séquences et des intervalles distincts. Le contrat refuse le rejeu réseau, les chevauchements et les mesures non synthétiques. La calibration technique enregistrée dans l'application est relue à la préparation : si elle est requise ou invalide, le simulateur transmet `calibration_required` sans valeurs, sans fabriquer une calibration réussie. La référence de banc `synthetic_reference` n'est jamais une calibration physique.

**Accepté par le broker** confirme l'accusé MQTT, pas l'écriture en base. Le rapport du panneau conserve cette distinction. La recette vivante du projet vérifie séparément les reçus PostgreSQL et la visibilité dans le dashboard. Les événements d'usage sélectionnés peuvent créer des notifications de simulation, sans interprétation médicale.

## Choisir les événements et les actions

Dans la configuration, cochez les événements automatiques à transmettre : rappel de pause, appui élevé, contact immobile ou absence de contact. Un scénario Intensif de 30 secondes produit un rappel vers 20 secondes ; Appuis élevés produit un événement vers 5 secondes. Ces délais sont ceux du démonstrateur Wokwi.

Pendant une transmission valide, le panneau de déclenchement ponctuel permet de choisir un événement et de l'ajouter à la prochaine fenêtre. Son origine `manual` reste distincte des événements calculés. Les fenêtres invalides, la calibration requise et les coupures ne produisent pas d'alertes d'usage valides. Une demande encore en attente lors de l'arrêt est annulée et apparaît dans le rapport.

Le worker contrôle l'identité de la souris, la qualité, les doublons et les préférences. Une notification d'un même type est limitée à une par minute et par souris. Le rappel de pause exige que les pauses soient activées et non reportées. Les trois autres événements restent dans le dashboard. Les notifications portent la mention Simulation. L'envoi externe de Web Push demeure désactivé dans le banc ; aucune réception téléphone ou montre n'est présumée.

Le panneau **Actions par persona** propose 37 actions et cinq parcours (suivi, prévention, support, sécurité et suppression). Chaque étape est choisie séparément : sélectionnez le persona et l'action, puis affichez son formulaire intégré. Connectez le bon compte si nécessaire, renseignez les champs et déclenchez l'action. Les listes d'identifiants viennent uniquement du périmètre autorisé de ce compte.

Le formulaire utilise les API normales de l'application et leur jeton CSRF : aucun compte privilégié ni secret de connexion n'est fourni au serveur du simulateur. Le formulaire intégré est de même origine et ses messages contrôlent la source, l'origine et un nonce. Le retour de connexion est limité aux destinations autorisées et lié au state OIDC. Les approbations distinctes, réauthentifications et preuves matérielles restent obligatoires ; une commande en attente n'est jamais affichée comme une opération physique réussie.

La confirmation de réception d'une alerte passe par une lecture authentifiée des notifications du compte utilisateur connecté, liée au numéro de l'exécution. Aucun compte ne peut demander les notifications d'un autre utilisateur. Le montage Wokwi est chargé dans une iframe externe isolée ; aucune donnée de compte ni de mesure ne lui est transmise par le simulateur.

Le catalogue et ses limites sont décrits dans [ACTIONS.md](ACTIONS.md). Après modification du catalogue, régénérer la copie statique : `../application/.venv/Scripts/python.exe actions_catalog.py --export ../application/app/static/simulation-catalog.json`.

Le partage avec un soignant reste une décision du compte utilisateur. Aucun accès médical n'est ajouté à l'employeur, au support ou à l'administration. Le panneau opérateur est limité à ce PC ; il n'est pas destiné à une publication Internet ou à des patients réels.

## Fichiers

- `engine.py`, `source_data/` : moteur, références minimales et empreintes SHA256.
- `server.py`, `transport.py` : commandes locales protégées contre les requêtes intersites, temps réel et mTLS.
- `static/` : panneau SKELIVIA adaptatif, logo et police d'origine réutilisés.
- `compose.yaml`, `prepare_transport.py` : service facultatif isolé et préparation opérateur.
- `.runtime/runs/` : rapports locaux, exclus de Git ; aucune donnée source n'est modifiée.
- `tests/` : comparaison native C++, agrégations, droits, transport et contrôles du serveur.
- [README-INFRA.md](README-INFRA.md) : commandes et limites d'exploitation.

Tests depuis ce dossier : `../application/.venv/Scripts/python.exe -m pytest tests -q`. La comparaison C++ nécessite un compilateur pris en charge ; les résultats indiquent explicitement si elle a été exécutée.

La [recette initiale](RECETTE.md) détaille la comparaison C++ et les premières vérifications PostgreSQL. La [recette des événements et actions](RECETTE_ACTIONS.md) documente les parcours des cinq personas. La [recette de la page unique](RECETTE_PAGE_UNIQUE.md) décrit l'interface simplifiée, ses courbes, les formulaires intégrés et les tests actuels.
