# Transport local du simulateur

Le simulateur reste dans le projet Docker `skelivia`. Son interface principale est servie par le proxy local sur `https://localhost:8443/simulateur/`. Le port `http://127.0.0.1:8774` reste lié au loopback pour les commandes locales et redirige sa page d'accueil vers HTTPS. MQTT reste privé : le service rejoint le réseau interne et présente uniquement le certificat client `skm-001`, associé à la souris synthétique `demo-device-a`. Aucune modification des autres projets Docker.

Le proxy résout le service facultatif à la demande, retire le préfixe `/simulateur/` et conserve l'origine HTTPS et `X-Forwarded-Prefix`. Son absence ne bloque pas le démarrage des dashboards. Le serveur du simulateur ne reçoit toujours aucun accès SQL. La seule page applicative autorisée dans une iframe est `/static/simulation.html`, avec `SAMEORIGIN` et `frame-ancestors 'self'` ; les autres pages restent interdites d'encadrement. Après changement de cette configuration, vérifier `nginx -t` puis redémarrer le proxy.

Le service rejoint également le réseau `edge` existant, nécessaire à Docker pour publier le port local lorsque le réseau privé est déclaré `internal: true`. Cela ne publie aucun port MQTT ; le seul bind du simulateur reste limité à l'adresse loopback.

Depuis la racine du dépôt, avec la pile SKELIVIA déjà démarrée :

```powershell
& dashboards/application/.venv/Scripts/python.exe dashboards/simulateur/prepare_transport.py
docker compose -f dashboards/application/infra/compose.yaml -f dashboards/simulateur/compose.yaml config --quiet
docker compose -f dashboards/application/infra/compose.yaml -f dashboards/simulateur/compose.yaml up -d --no-deps simulator
```

Si Docker Desktop tourne sous un autre compte Windows, ajouter à la préparation `--operator-account 'DOMAINE\Compte'`. Les permissions du dossier `.runtime` sont limitées au compte opérateur, au compte exécutant la préparation, à SYSTEM et aux administrateurs. Les fichiers runtime ne sont pas versionnés.

La préparation utilise ponctuellement le service opérateur `migrate` pour lire les versions et l'état technique du seul appareil fictif autorisé. Elle contrôle son association, le numéro de certificat, son expiration et sa révocation. Elle ne modifie jamais une calibration. Après une calibration, une mise à jour ou un renouvellement de certificat, refaire la préparation puis la commande `up -d --no-deps --force-recreate simulator` avec les deux mêmes fichiers Compose, avant un nouveau scénario : le bind du fichier remplacé doit être rechargé. Un état `required` reste `required` ; il ne constitue pas une preuve de calibration.

Le serveur ne reçoit aucun identifiant PostgreSQL, contenu médical ou clé privée d'autorité. La source du simulateur, les ressources de marque, le certificat client, sa clé et l'autorité publique sont montés en lecture seule. Seul `.runtime/runs` est inscriptible, sous `/run/simulator-runs`, pour les rapports JSON des scénarios. Le processus hérite de l'utilisateur non privilégié de l'image applicative ; les capacités Linux sont retirées et les journaux d'accès HTTP désactivés.

Variables de transport : `SIMULATOR_CONFIG_FILE=/run/simulator/transport.json`, `SIMULATOR_MQTT_HOST=broker`, `SIMULATOR_MQTT_PORT=8883`, `SIMULATOR_MQTT_CA_FILE=/run/pki/ca.pem`, `SIMULATOR_MQTT_CERT_FILE=/run/device/cert.pem`, `SIMULATOR_MQTT_KEY_FILE=/run/device/key.pem`. Les rapports utilisent `SIMULATOR_OUTPUT_DIR=/run/simulator-runs` ; les ressources approuvées utilisent `SIMULATOR_BRAND_DIR=/srv/brand`.

Un accusé MQTT confirme uniquement l'acceptation par le broker. La preuve d'enregistrement nécessite une lecture opérateur distincte de `transport_ingest_receipt`, filtrée sur le `run_id` (UUID de session), puis la vérification des rapports associés. Le serveur web du simulateur n'obtient pas cet accès. Les fenêtres d'agrégats, contrôles de fraîcheur, séquences et contraintes anti-chevauchement restent ceux du contrat d'ingestion existant.

Pour vérifier une session, remplacer l'UUID ci-dessous par le `run_id` affiché dans le rapport :

```powershell
& dashboards/application/.venv/Scripts/python.exe dashboards/simulateur/prepare_transport.py --verify-run '00000000-0000-0000-0000-000000000000'
```

Le résultat borné contient le nombre de reçus, les séquences, les identifiants de rapports et leur qualité, sans contenu de mesures. Il est enregistré dans `.runtime/runs/<run_id>.receipt.json`. Un nombre nul ne constitue pas une preuve de réception ; comparer le nombre positif obtenu aux fenêtres annoncées acceptées par le broker.

L'interface est un banc local synthétique, sans validation clinique ou connexion à un patient réel. Les certificats sont ceux du banc de développement. Le port HTTP local n'est pas destiné à être publié sur le réseau.

Vérifications du transport :

```powershell
& dashboards/application/.venv/Scripts/python.exe -m pytest dashboards/simulateur/tests/test_transport_config.py -q
docker compose -f dashboards/application/infra/compose.yaml -f dashboards/simulateur/compose.yaml ps simulator
```

Arrêter seulement le simulateur :

```powershell
docker compose -f dashboards/application/infra/compose.yaml -f dashboards/simulateur/compose.yaml stop simulator
```
