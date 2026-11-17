# Moteur déterministe SKELIVIA

`engine.py` ne dépend que de Python standard. Aucun réseau, compte patient, identifiant de souris, horloge système ou publication n'est utilisé. Toute sortie porte `synthetic: true` : c'est un scénario de démonstration, y compris lorsqu'il rejoue une trace de référence acquise avec phyphox. Aucun seuil n'est présenté comme seuil médical.

## Interface serveur

```python
from engine import catalog, build_run

options = catalog()
run = build_run({
    "source": "wokwi",
    "mode": "intensive",
    "duration_seconds": 30,
    "step_ms": 50,
    "include_samples": False,
})
```

Configuration fermée : champ inconnu → `ValueError`. Durée entière 5 à 300 secondes, multiple de cinq. `step_ms` doit être 50 : le rythme natif Wokwi est fixe. Le rejeu phyphox utilise toujours ses horodatages natifs, pas ce pas de simulation. Le moteur calcule hors ligne immédiatement ; le serveur est seul responsable d'une éventuelle publication en temps réel à la cadence des fenêtres. Ne pas injecter toutes les fenêtres avec le même horodatage.

Sources :

- `wokwi` avec `mode` parmi `manual`, `normal`, `intensive`, `force`, `immobile`, `invalid`, `network_cut` ; défaut normal.
- `phyphox` avec `dataset_id` parmi `usage`, `postures`, `independent` ; défaut usage. Mode Wokwi sans effet dans cette source et provenance `native_timestamp_replay`.
- `manual` facultatif pour le mode manuel : `ax/ay/az` en m/s², `gx/gy/gz` en rad/s (nombres finis, valeur absolue ≤100), `thumb/palm` entiers ADC 0..4095, `contact` booléen. Paramètres constants pendant un run ; valeurs hors domaine physique des capteurs sont déclarées invalides par le pipeline. Les paramètres finaux figurent dans provenance.manual.
- `replay_assumptions` facultatif, soit null, soit objet complet `{thumb:1000,palm:1200,contact:true}`. Les trois valeurs sont des hypothèses synthétiques, jamais des données phyphox. Sans cet objet, pression/contact sont invalides et **toutes les métriques des fenêtres sont nulles**, tout en permettant d'examiner les épisodes gyro séparés.
- `include_samples` booléen facultatif, faux par défaut ; activation réservée à l'inspection locale du signal.
- `fault_sensor` : `all` par défaut, ou `thumb`, `palm`, `motion`, `contact` uniquement avec `source:wokwi` et `mode:invalid`. Le choix `all` conserve la panne historique pouce/paume/mouvement, avec contact fonctionnel. Une panne ciblée reprend le signal Normal et invalide uniquement le canal choisi. C'est une extension du simulateur local, pas une modification du montage Wokwi externe.

`catalog()` fournit `sources`, `modes`, `datasets[{id,label,gyro,accel}]`, contraintes `duration_seconds`, `step_ms`, `window_seconds`, `manual_defaults`, `balance_reference`, `limitations`. Aucune entrée utilisateur n'est interprétée comme chemin de fichier.

## Résultat

`build_run` renvoie :

- `windows[]` : `{index,start_seconds,end_seconds,duration_seconds:5,quality,metrics,events,publish,synthetic:true,valid_seconds,missing_seconds}`. Fenêtres contiguës sans chevauchement. `quality` est valid ou invalid. `metrics` possède toujours `contact_seconds,episodes,thumb_pct,palm_pct` ; les quatre valent null si une fraction de la fenêtre est manquante/invalide. Le serveur ajoute ses dates absolues, sa session et son numéro de séquence, sans remplacer ces indicateurs de qualité.
- `summary` : durée, nombre d'échantillons traités, fenêtres valides/invalides, épisodes gyro confirmés, activité d'accélération secondaire, lacunes d'acquisition et fenêtres publiables. `publishable_windows` indique l'autorisation de transport, **pas** la validité de mesure : le mode invalid doit pouvoir tester le contrat des paquets invalides.
- `provenance` : source, mode, dataset, références `{file,source,sha256,bytes}`, paramètres manuels ou hypothèses du rejeu, règles et limites, références balance exploratoires.
- `events_expected[]` : événements calculés par le scénario, sous forme `{kind,at_seconds,...}`. Types gyro_episode, high_force, pause_reminder, quiet_contact, absent, network_cut. Un épisode comporte début, durée et chemin angulaire ; ces événements ne sont ni des gestes identifiés ni des diagnostics. Ce tableau constitue une attente du scénario, pas une preuve que l'application l'a reçu.
- `samples[]`, si demandé : temps relatif, temps original phyphox ou null, vrai dt, axes, validité des canaux, norme gyro filtrée, compteurs de diagnostic et drapeaux. Les valeurs non finies sont sérialisées null ; JSON strict sans NaN.

## Calcul et continuité

Le port reprend le `pipeline.h` actuel : EMA gyro alpha 0,2 ; hystérésis 0,05/0,025 rad/s ; durée minimale 500 ms ; chemin minimal 0,05 rad ; confirmation à la sortie de l'épisode. Ces valeurs sont celles du démonstrateur. Le compteur d'accélération est distinct et jamais ajouté au gyro. Les calculs sensibles utilisent explicitement le flottant IEEE binary32.

Les presets Wokwi reprennent exactement leurs valeurs et phases de 50 ms. Les horodatages des drapeaux suivent le code C++ : un échantillon à t décrit ici l'intervalle `[t,t+50ms)` et son update porte dt=50 ms, comme la référence (ainsi la force soutenue peut s'activer à t=4,95 s). La durée de contact des fenêtres est intégrée à partir des échantillons, jamais récupérée du compteur de contact continu du pipeline. Les épisodes par fenêtre sont les confirmations dans cette fenêtre, jamais le total cumulatif. Les pressions ADC/% sont pondérées par la durée de chaque fraction de fenêtre, zéro valide compris ; elles ne représentent pas des grammes.

Phyphox : conservation des temps gyro d'origine et de leurs dt variables. L'origine relative est le premier temps gyro. L'accélération est alignée par interpolation linéaire seulement entre deux voisins distants d'au plus 0,2 s, jamais extrapolée. Aucune interpolation du gyro, aucun rééchantillonnage à 20 Hz. Un dt supérieur à 0,2 s casse le segment : aucun épisode interrompu ne peut être confirmé, aucune durée manquante n'est intégrée. Les mesures présentes sont intégrées sur leur intervalle précédent, découpé aux frontières de 5 secondes. Le dt du pipeline est arrondi à la milliseconde, avec rupture forcée pour toute vraie lacune >0,2 s ; l'intégration des métriques conserve les dt en secondes. Un échantillon après la fin demandée peut fermer le dernier intervalle, limité à cette fin ; les événements postérieurs ne sont pas inclus.

`network_cut` conserve le signal local mais met `publish:false` sur toutes les fenêtres du run et produit un événement de coupure. Une reprise exige un nouveau run ; aucun rattrapage automatique des fenêtres coupées n'est effectué.

## Présentation dynamique des capteurs

Les points `chart_samples` exposent `sensor_states` pour `thumb`, `palm`, `motion` et `contact`. Les états `active`, `rest`, `high`, `fault` et `unknown` sont calculés depuis les échantillons du moteur. Seule une panne explicitement injectée reçoit `fault`. Une donnée non mesurée, invalide sans panne injectée, ou située sur une lacune reste `unknown`. Un appui relatif valide d'au moins 70 % reçoit `high` ; cette couleur ne signifie pas que l'événement d'appui soutenu s'est déjà déclenché.

`contact_seconds` et `quiet_seconds` sont les compteurs du démonstrateur, non des horloges du navigateur. Le compteur de contact est remis à zéro après trois secondes d'absence ; il ne représente donc ni un temps exact de contact continu ni un temps total de travail. `motion_active` reprend l'activité du pipeline et ne décrit pas une trajectoire physique. Les compteurs indisponibles restent nuls au sens JSON (`null`), jamais remplacés par zéro. Les drapeaux `flags` indiquent les conditions effectivement atteintes dans le moteur. La sélection des événements à transmettre reste une décision séparée.

La panne injectée produit un événement local `sensor_fault` à l'instant zéro avec la liste des canaux concernés. Il est inclus dans le plan et filtré par l'horloge dans `detected_events`, mais ne fait pas partie des événements transmis en MQTT. Le contrat de télémétrie applicatif est inchangé. L'aperçu contient le plan complet, clairement séparé des observations en cours.

## Références et vérification

`source_data/manifest.json` identifie les copies minimales issues de `work/p1_sauvegarde_collecte_20261112/projet1` : pipeline, trois paires CSV gyro/accélération et CSV des lectures de balance. Chaque fichier est vérifié par SHA256 à chaque construction/catalogue ; modification silencieuse refusée. Aucune vidéo copiée. Les indications pouce 189/361/344 g et paume 485/699/849 g restent des relevés ponctuels exploratoires avec leurs notes d'origine ; **aucune conversion g→ADC ou % n'est possible sans calibration FSR propre**.

Tests :

```text
python -m pytest dashboards/simulateur/tests/test_engine.py -q
```

La comparaison native compile le pipeline copié et exécute son self-test, puis compare 4 200 ticks des sept modes : épisodes, accélération, alertes, norme gyro, chemin angulaire et pourcentage pouce. Compilateur MSVC local détecté et utilisé avec `/fp:strict` ; ce test n'a pas été sauté lors de la validation initiale. En absence de compilateur local, seul ce test est explicitement skipped, les autres restent exécutables. Les exécutables sont créés dans le répertoire temporaire pytest, pas livrés comme code moteur.
