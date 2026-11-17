# Catalogue des actions du simulateur

Le catalogue public `actions_catalog.py` décrit 37 choix couvrant les 33 commandes métier existantes et les deux exports autorisés. Les réglages sont répartis en trois choix pour respecter les droits : accessibilité pour tous, pauses et notifications pour l’utilisateur uniquement.

Le catalogue ne lit pas la base et n’exécute rien. Les identifiants à sélectionner proviennent de `/api/workspace` dans la fenêtre de l’application authentifiée. Ils ne doivent pas être récupérés dans le serveur du simulateur ni envoyés à celui-ci. Les API métier conservent leurs contrôles de rôle, de relation de suivi, de partage, d’affectation et de réauthentification.

## Contrat d’interface

- `GET /api/actions/catalog` peut exposer `catalog()` depuis le serveur du simulateur. La copie publique `application/app/static/simulation-catalog.json` est destinée à la fenêtre authentifiée.
- Chaque action fournit `id`, `action`, `roles`, `method`, `path`, `fields`, `description`, `effect` et `limitations`.
- Pour une commande : envoyer `{action, payload}` à `/api/actions`, avec le jeton CSRF de la session connectée. Le catalogue n’accorde aucune autorisation.
- `fields[].source` décrit une collection du workspace courant, sa clé et son libellé. `filters` contient uniquement des égalités locales ; les filtres ne remplacent jamais l’autorisation serveur.
- Un champ facultatif laissé vide est omis. Ne pas envoyer de chaîne vide à la place d’un identifiant facultatif.
- `payload_path`, utilisé pour `channels.pause` et les autres canaux, décrit la construction de l’objet imbriqué. Ne pas envoyer littéralement la clé avec un point à l’API.
- `default: "today"` sur un champ `date` signifie la date UTC courante au moment de l’affichage, pas une date figée dans le fichier.
- Les exports utilisent `/api/export`, avec `fixed_payload.kind` et les dates éventuelles en paramètres. Le fichier reste téléchargé dans l’application authentifiée ; son contenu ne retourne pas au simulateur.
- Les cinq parcours sont des listes de choix successifs : chaque étape requiert un clic explicite et le compte autorisé. Aucun clic n’approuve automatiquement l’étape suivante.

## Limites conservées

Un ticket matériel, une calibration, une mise à jour, un remplacement ou une opération de certificat garde son état réel en attente tant que l’adaptateur n’a pas fourni une preuve recevable. Les cases de contrôle ne sont pas précochées. Les champs de preuve et de résultats de tests ne sont pas préremplis avec un succès fictif.

Les opérations de compte et les approbations de correctif exigent toujours les personnes distinctes et la réauthentification prévues. Les demandes de suppression ne réalisent pas l’effacement dans le simulateur. Un signalement synthétique teste le circuit des incidents ; il ne teste pas la détection d’une attaque réseau. Le contrôle d’accès porte sur la base applicative et ne prouve pas une sauvegarde restaurable ou une règle de pare-feu.

Les canaux téléphone/montre enregistrent les préférences existantes. Une préférence n’est pas une preuve d’envoi externe ni de réception sur un appareil.

## Mise à jour et vérification

Depuis `dashboards/simulateur` :

```powershell
& '../application/.venv/Scripts/python.exe' actions_catalog.py --export ../application/app/static/simulation-catalog.json
& '../application/.venv/Scripts/python.exe' -m pytest tests/test_actions_catalog.py -q
```

Les tests comparent les commandes et les champs avec les modèles stricts du domaine, vérifient les restrictions de rôles importantes, les parcours et la copie statique. Ils ne déclarent pas qu’une opération a été réalisée sur le banc Docker.
