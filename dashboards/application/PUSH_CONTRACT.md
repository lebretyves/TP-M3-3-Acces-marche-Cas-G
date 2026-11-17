# Web Push — intégration et limites

Backend : `install_push(app, factory, account_dep, csrf_dep)` dans `app.push`. Modèles enregistrés avant migration via `app.push_models`. Dépendance transport : `pywebpush==2.5.0` (MPL-2.0). Worker : `python -m app.push --loop`, rôle SQL dédié `skelivia_push`, cycle 30 secondes, aucune lecture des documents/mesures.

## Routes authentifiées, propriétaire uniquement

- `GET /api/push/config` : `{configured,public_key,reason,watch:"os_mirroring_only",subscriptions:[{id,label,active,created_at}],deliveries:[{id,kind,status,attempts,updated_at}]}`. Aucun endpoint ni clé d'abonnement renvoyé.
- `POST /api/push/subscribe` + CSRF : `{endpoint,keys:{p256dh,auth},label}`. Clés P-256/auth validées, endpoint HTTPS fournisseur connu uniquement, huit abonnements actifs maximum. L'identité vient exclusivement de la session. Un endpoint associé à un autre compte ne peut pas être réattribué, même désactivé. Réponse `{ok:true,id}`.
- `POST /api/push/unsubscribe` + CSRF : `{id}`. Désactivation propre au titulaire, idempotente. Réponse `{ok:true}`.

Une activation doit résulter d'un clic utilisateur. Le frontend n'appelle jamais `Notification.requestPermission` au chargement. Il transmet seulement les champs ci-dessus de `PushSubscription.toJSON()`, pas `expirationTime` ni un `owner_id`. Aucune donnée API ni médicale ne doit être mise en cache par le Service Worker.

## Confidentialité et livraison

Payload chiffré Web Push : `{kind:"pause|advice|report|support|calibration",title:"SKELIVIA",body:"Une information est disponible dans votre espace.",url:"/?notifications=1",silent:false}`. Le worker ne copie jamais un titre de document, un patient, une mesure, une conclusion ou le texte d'une notification interne. Le Service Worker peut ignorer les textes réseau et sélectionner ses propres libellés génériques fixes. L'ouverture recharge l'application et son contrôle d'authentification.

Les alertes de nouvelle connexion/sécurité restent exclusivement dans le dashboard. Les réglages du compte et son activité sont revérifiés au moment du traitement. Une notification déjà lue, un abonnement révoqué ou un compte inactif annule l'envoi. Les horaires silencieux, exprimés dans `SKELIVIA_TIMEZONE` (Europe/Paris par défaut), suppriment l'envoi externe ; la notification demeure dans le dashboard.

Les canaux `phone` et `both` autorisent l'envoi aux navigateurs explicitement abonnés. La destination physique est le navigateur sur lequel le titulaire active l'abonnement ; le backend ne prétend pas détecter un téléphone. La duplication vers une montre dépend des réglages et capacités du système. **Le canal montre seule n'est pas réalisable indépendamment par ce Web Push** : état `unsupported_watch_only`, sans substitution silencieuse vers le téléphone.

États : `pending`, `retry`, `configuration_required`, `accepted_by_provider`, `quiet_suppressed`, `channel_disabled`, `unsupported_watch_only`, `cancelled`, `expired`, `revoked`, `failed`. `accepted_by_provider` confirme uniquement l'acceptation par le fournisseur, pas la réception ou lecture sur téléphone/montre. Au maximum trois tentatives, délai progressif, expiration 24 h, TTL fournisseur 60 s. Les erreurs 404/410 désactivent l'abonnement. Aucun corps d'erreur fournisseur ni URL secrète n'est journalisé.

Le transport refuse toute redirection et tout proxy issu de l'environnement, exige TLS vérifié et une résolution publique des seuls fournisseurs autorisés. L'endpoint et les clés sont chiffrés dans la base. Les livraisons portent uniquement des identifiants techniques et états.

## Activation de déploiement

`SKELIVIA_PUSH_ENABLED=false` par défaut : aucun envoi réel pendant la réalisation ou les tests. Fournir ultérieurement un domaine HTTPS accessible depuis le téléphone, un certificat reconnu, un contact VAPID réel et les variables suivantes :

- `SKELIVIA_VAPID_PRIVATE_KEY_FILE` : secret PEM EC P-256 ; jamais dans Git.
- `SKELIVIA_VAPID_PUBLIC_KEY_FILE` : clé publique EC non compressée, 65 octets encodés base64url.
- `SKELIVIA_VAPID_SUBJECT` : contact `mailto:` réel de l'opérateur, pas une adresse inventée.
- `SKELIVIA_PUSH_ENABLED=true` seulement après configuration et activation explicite par l'utilisateur.

Le serveur valide que les deux clés correspondent. `localhost` désigne le téléphone lui-même lorsqu'on l'ouvre sur celui-ci : l'URL de développement du PC ne constitue pas un déploiement mobile. Sur iPhone/iPad compatibles, l'application web doit être ajoutée à l'écran d'accueil pour ce parcours. Aucun appareil physique, compte fournisseur ou notification réelle n'a été utilisé pour les tests.

Ces paramètres et les montages de clés doivent être configurés pour l'API qui propose l'abonnement **et** pour le processus `push` qui envoie. Le réseau Compose privé actuel n'autorise pas la sortie Internet du worker push ; le déploiement devra prévoir une sortie contrôlée vers les fournisseurs autorisés. Modifier uniquement `SKELIVIA_PUSH_ENABLED` ne suffit donc pas. Ne pas publier les ports PostgreSQL ou MQTT pour activer les notifications.

## Sources primaires vérifiées

- Le [projet officiel pywebpush](https://github.com/web-push-libs/pywebpush) documente la souscription, AES128GCM, VAPID, délais et transport. La [distribution PyPI 2.5.0](https://pypi.org/project/pywebpush/2.5.0/) précise version et licence.
- [Apple : Web Push pour les applications et navigateurs](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers) décrit le geste explicite, les applications d'écran d'accueil à partir d'iOS 16.4, les Service Workers et les états fournisseur.
- [W3C Push API](https://www.w3.org/TR/push-api/) décrit la relation application, service de push et Service Worker ; la version consultée est un Working Draft, pas une garantie de compatibilité de chaque appareil.
