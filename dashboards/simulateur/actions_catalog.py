"""Public command descriptions for the local simulator, never an execution API.

Workspace choices must be resolved in the authenticated application window. This
module contains no account identifiers, credentials, database access or commands
that bypass the existing domain authorization.
"""
from copy import deepcopy


ROLES = ['user', 'clinician', 'employer', 'support', 'security']
LABELS = dict(zip(ROLES, ['Utilisateur / patient', 'Soignant', 'Employeur / prévention', 'Support', 'Administration sécurité']))


def field(name, label, type='text', *, required=True, **kwargs):
    return {'name': name, 'label': label, 'type': type, 'required': required, **kwargs}


def options(*pairs):
    return [{'value': value, 'label': label} for value, label in pairs]


def choice(name, label, *pairs, **kwargs):
    return field(name, label, 'select', options=options(*pairs), **kwargs)


def reference(name, label, collection, *, value='id', display='title', required=True, **kwargs):
    filters = kwargs.pop('filters', {})
    return field(name, label, 'select', required=required,
                 source={'collection': collection, 'value': value, 'label': display, 'filters': filters}, **kwargs)


def text(name, label, *, required=True, **kwargs):
    return field(name, label, 'textarea', required=required, max_length=2000, **kwargs)


def action(id, label, roles, fields, description, effect, *, command=None, limitations='', **kwargs):
    return {'id': id, 'action': command or id, 'label': label, 'roles': roles,
            'description': description, 'effect': effect, 'limitations': limitations,
            'method': 'POST', 'path': '/api/actions', 'fields': fields, **kwargs}


def catalog():
    """Return fresh serializable metadata; GET does not execute or create data."""
    title = lambda: field('title', 'Titre', max_length=160)
    body = lambda: text('body', 'Texte de démonstration à saisir')
    reason = lambda: text('reason', 'Motif à saisir')
    ticket = lambda name='id': reference(name, 'Ticket autorisé', 'tickets')
    patient = lambda: reference('patient_id', 'Patient suivi', 'patients', display='name')
    incident = lambda: reference('id', 'Incident', 'incidents')
    recommendation = lambda: reference('id', 'Recommandation', 'recommendations')
    category = lambda: choice('category', 'Type d’aménagement', ('equipment', 'Matériel'), ('layout', 'Poste de travail'), ('organisation', 'Organisation'))
    date_field = lambda name, label: field(name, label, 'date', default='today')
    acts = [
        action('settings.accessibility', 'Adapter les textes et les contrastes', ROLES,
               [field('large_text', 'Grands textes', 'boolean', default=False), field('high_contrast', 'Contrastes renforcés', 'boolean', default=False)],
               'Modifier les préférences du compte connecté.', 'Préférences enregistrées pour ce compte.', command='settings.save'),
        action('settings.pauses', 'Régler les rappels de pause', ['user'],
               [field('pause_enabled', 'Activer les rappels', 'boolean', default=True), field('pause_minutes', 'Intervalle en minutes', 'integer', default=45, min=5, max=180)],
               'Choisir si les rappels sont actifs et leur intervalle.', 'Préférences de pause enregistrées.', command='settings.save'),
        action('settings.notifications', 'Choisir les canaux et horaires silencieux', ['user'],
               [choice('channels.'+kind, label, ('none', 'Aucun'), ('phone', 'Téléphone'), ('watch', 'Montre'), ('both', 'Les deux'),
                       payload_path=['channels', kind], default='none')
                for kind, label in [('pause', 'Rappels de pause'), ('advice', 'Conseils'), ('report', 'Bilans'), ('support', 'Support'), ('calibration', 'Calibration')]]
               + [field('quiet_start', 'Début du silence', 'time', default='19:00'), field('quiet_end', 'Fin du silence', 'time', default='08:00')],
               'Paramétrer les notifications déjà prévues dans le projet.', 'Préférences enregistrées.', command='settings.save',
               limitations='Un canal sélectionné ne prouve pas une livraison. Web Push doit être configuré ; la montre dépend du relais du téléphone.'),
        action('notification.read', 'Marquer une notification comme lue', ROLES,
               [reference('id', 'Notification personnelle', 'notifications')],
               'Choisir une notification du compte connecté.', 'Notification marquée comme lue.'),
        action('pause.snooze', 'Reporter les rappels de pause', ['user'],
               [field('minutes', 'Report en minutes', 'integer', default=15, min=1, max=120)],
               'Suspendre temporairement les rappels.', 'Report enregistré pour le compte connecté.'),
        action('share.create', 'Autoriser un partage au soignant', ['user'],
               [reference('clinician_id', 'Soignant habilité', 'clinicians', display='name'), date_field('start', 'Début de période'), date_field('end', 'Fin de période'),
                field('categories', 'Mesures partagées', 'multiselect', options=options(('contact', 'Temps de contact'), ('pressure', 'Appuis relatifs'), ('moves', 'Mouvements')), default=['contact', 'pressure', 'moves']),
                field('duration_hours', 'Durée du partage en heures', 'integer', default=24, min=1, max=2160)],
               'Sélectionner le soignant, la période et les catégories autorisées.', 'Partage actif borné par sa période et sa date d’expiration.', limitations='Le soignant doit déjà être lié au patient. La période ne peut pas finir dans le futur.'),
        action('share.revoke', 'Révoquer un partage', ['user'],
               [reference('id', 'Partage personnel', 'shares', display='clinician_id')],
               'Retirer un partage existant.', 'Accès futur correspondant révoqué ; les copies déjà exportées ne sont pas récupérées.'),
        action('document.publish', 'Publier ou corriger un conseil / bilan', ['clinician'],
               [patient(), choice('kind', 'Document', ('advice', 'Conseil de prévention'), ('report', 'Bilan de fin de suivi')), title(), body(),
                reference('document_id', 'Série existante à corriger (facultatif)', 'documents', value='document_id', required=False)],
               'Le soignant saisit le contenu destiné au patient.', 'Nouvelle version datée et notification au patient.',
               limitations='Partage actif requis. Une correction conserve le type, le patient et l’auteur de la série. Aucun diagnostic automatique.'),
        action('reminder.create', 'Créer un rappel de réexamen', ['clinician'],
               [patient(), date_field('due', 'Date de réexamen'), body()],
               'Programmer un rappel personnel sur un patient suivi.', 'Rappel visible dans l’espace soignant.', limitations='Le rappel ne prolonge pas les droits sur les données.'),
        action('reminder.delete', 'Retirer un rappel de réexamen', ['clinician'],
               [reference('id', 'Rappel personnel', 'reminders', display='body')],
               'Choisir un rappel créé par le compte connecté.', 'Rappel retiré de la liste active.'),
        action('recommendation.publish', 'Publier une recommandation à l’employeur', ['clinician'],
               [reference('org_id', 'Organisation liée', 'organisations', display='id'), title(), body(), category()],
               'Décrire un aménagement sans données médicales individuelles.', 'Recommandation à traiter et notification dans l’espace employeur.'),
        action('recommendation.revise', 'Corriger une recommandation', ['clinician'],
               [recommendation(), title(), body(), category()],
               'Modifier une recommandation du soignant connecté.', 'Historique conservé et notification à l’employeur.'),
        action('recommendation.status', 'Modifier l’avancement d’une recommandation', ['employer'],
               [recommendation(), choice('status', 'Avancement', ('todo', 'À traiter'), ('in_progress', 'En cours'), ('done', 'Réalisée'), ('blocked', 'Bloquée'))],
               'Choisir une recommandation de son organisation.', 'Statut et historique actualisés, visibles par le soignant auteur.'),
        action('ticket.create', 'Ouvrir un ticket technique', ['user', 'clinician'],
               [title(), body(), choice('category', 'Problème', ('connection', 'Connexion'), ('calibration', 'Calibration'), ('replacement', 'Remplacement'), ('loss', 'Perte'), ('software', 'Logiciel')),
                reference('device_id', 'Souris personnelle (facultatif)', 'devices', display='id', required=False)],
               'Décrire uniquement le problème technique rencontré.', 'Ticket créé et attribué si un support habilité est disponible.',
               limitations='Le soignant choisit uniquement Logiciel, sans souris de patient. Déclarer une perte ne révoque pas à lui seul un certificat.'),
        action('ticket.reply', 'Répondre à un ticket', ['user', 'clinician', 'support'],
               [ticket(), body()], 'Ajouter une réponse technique au ticket autorisé.', 'Message ajouté et notification au destinataire.'),
        action('ticket.status', 'Changer le statut d’un ticket', ['support'],
               [ticket(), choice('status', 'Statut', ('in_progress', 'En cours'), ('waiting', 'En attente'), ('resolved', 'Résolu'))],
               'Mettre à jour un ticket attribué au support connecté.', 'Statut actualisé et notification au propriétaire.',
               limitations='Un ticket matériel ne peut être résolu sans diagnostic actif, contrôles et calibration physique vérifiée. Une référence synthétique ne suffit pas.'),
        action('ticket.checks', 'Enregistrer les contrôles après intervention', ['support'],
               [ticket(), field('connection', 'Connexion vérifiée', 'boolean', default=False), field('sensors', 'Capteurs vérifiés', 'boolean', default=False), field('calibration', 'Calibration vérifiée', 'boolean', default=False)],
               'Consigner les contrôles réellement effectués.', 'Contrôles enregistrés sur le ticket attribué.',
               limitations='Diagnostic actif obligatoire. Ces cases ne remplacent pas une preuve matérielle.'),
        action('diagnostic.request', 'Demander un diagnostic temporaire', ['support'],
               [ticket(), field('duration_minutes', 'Durée en minutes', 'integer', default=15, min=1, max=60), reason()],
               'Demander au propriétaire du ticket l’accès technique temporaire.', 'Demande en attente et notification au propriétaire ; accès encore fermé.'),
        action('diagnostic.approve', 'Autoriser le diagnostic demandé', ['user'],
               [reference('id', 'Demande de diagnostic en attente', 'jobs', display='kind', filters={'kind': 'diagnostic_request', 'status': 'awaiting_approval'})],
               'Le propriétaire approuve la demande choisie.', 'Accès technique ouvert pour la durée demandée, sans données de santé.'),
        action('diagnostic.revoke', 'Fermer un diagnostic temporaire', ['support', 'security'],
               [field('id', 'Identifiant du ticket concerné', max_length=80, help='Support : recopier l’identifiant du ticket attribué. Sécurité : utiliser la référence technique de l’intervention ; aucun dossier patient n’est exposé.')],
               'Retirer un accès technique temporaire existant.', 'Diagnostic fermé.', limitations='La référence reste contrôlée côté serveur selon le rôle.'),
        action('device.calibrate', 'Demander une calibration', ['user', 'support'],
               [reference('device_id', 'Souris autorisée', 'devices', display='id'), ticket('ticket_id') | {'required': False}],
               'Créer une commande de calibration pour l’appareil autorisé.', 'Commande en attente de l’adaptateur matériel.',
               limitations='Le support doit préciser son ticket avec diagnostic actif. Aucun résultat physique n’est inventé.'),
        action('device.replace', 'Demander le remplacement d’une souris', ['support'],
               [ticket('ticket_id'), field('new_device_id', 'Identifiant de la nouvelle souris', max_length=80)],
               'Préparer le remplacement dans une intervention attribuée.', 'Commande en attente de vérification par l’adaptateur.',
               limitations='Diagnostic actif requis et nouvel identifiant encore non associé. Aucune association réussie n’est présumée.'),
        action('device.update', 'Demander une mise à jour approuvée', ['support'],
               [ticket('ticket_id'), reference('patch_id', 'Correctif approuvé', 'approved_patches')],
               'Lancer une demande pour une version déjà approuvée.', 'Commande en attente de résultat technique vérifié.', limitations='Diagnostic actif requis. L’envoi ne prouve pas l’installation.'),
        action('security.report', 'Signaler une anomalie technique', ['user', 'clinician', 'support'],
               [body(), ticket('ticket_id') | {'required': False}],
               'Transmettre un signalement technique minimal sans contenu médical.', 'Événement à examiner dans l’administration sécurité.', limitations='Le signalement de démonstration ne prouve pas une intrusion réelle.'),
        action('incident.qualify', 'Qualifier un incident', ['security'],
               [incident(), choice('status', 'Qualification', ('confirmed', 'Confirmé'), ('false_positive', 'Fausse alerte')), reason()],
               'Examiner un événement encore non qualifié.', 'Qualification et chronologie enregistrées.'),
        action('incident.action', 'Consigner une action sur un incident', ['security'],
               [incident(), body()], 'Décrire une action effectuée sur un incident confirmé.', 'Action ajoutée à la chronologie.', limitations='Cette action consigne un traitement ; elle ne lance pas une commande système.'),
        action('incident.close', 'Clôturer un incident avec une vérification', ['security'],
               [incident(), text('proof', 'Vérification réalisée et référence de preuve')],
               'Enregistrer le contrôle effectué après le traitement.', 'Incident clôturé avec sa chronologie.', limitations='Incident confirmé et action préalable obligatoires. Ne pas inventer de preuve.'),
        action('account.request', 'Demander une opération sur un compte', ['security'],
               [choice('operation', 'Opération', ('create', 'Créer'), ('suspend', 'Suspendre'), ('reactivate', 'Réactiver'), ('role', 'Changer le rôle')),
                reference('target_id', 'Compte existant (sauf création)', 'accounts', display='name', required=False),
                choice('role', 'Rôle pour création ou changement', *[(r, LABELS[r]) for r in ROLES], required=False),
                field('name', 'Nom pour une création', required=False, max_length=160), field('username', 'Identifiant pour une création', required=False, max_length=80),
                field('org_id', 'Organisation pour une création', required=False, max_length=80), reason()],
               'Préparer une demande sans modifier immédiatement les droits.', 'Demande en attente d’un administrateur distinct.',
               limitations='Réauthentification récente requise. Création : identité, rôle et organisation obligatoires. Une suspension ne cible pas son propre compte.'),
        action('account.approve', 'Approuver une demande de compte', ['security'],
               [reference('id', 'Demande de compte', 'account_requests', display='operation')],
               'Un second administrateur examine la demande.', 'Opération appliquée ou provisionnement en attente selon la demande.',
               limitations='Approbateur distinct du demandeur et de la cible, identité récemment vérifiée. La création reste inactive avant l’enrôlement.'),
        action('session.revoke', 'Couper une session autorisée', ['user', 'clinician', 'support', 'security'],
               [reference('id', 'Session', 'sessions', display='account_id'), reason()],
               'Choisir une session visible dans le périmètre du compte.', 'Session révoquée immédiatement.', limitations='Une révocation de sa session courante déconnecte cette fenêtre. Pour un tiers, réauthentification sécurité récente requise.'),
        action('certificate.request', 'Demander une opération de certificat', ['security'],
               [reference('device_id', 'Souris du registre', 'certificates', value='device_id', display='device_id'), choice('operation', 'Opération', ('renew', 'Renouveler'), ('revoke', 'Révoquer')), reason()],
               'Créer une demande pour l’opérateur PKI.', 'Commande en attente de l’adaptateur de certificats.', limitations='Réauthentification récente requise. Aucun certificat n’est déclaré installé ou révoqué par ce seul clic.'),
        action('patch.evaluate', 'Évaluer ou approuver une mise à jour', ['security'],
               [reference('id', 'Mise à jour', 'patches'), choice('priority', 'Priorité', ('low', 'Faible'), ('medium', 'Moyenne'), ('high', 'Élevée'), ('critical', 'Critique')),
                text('exposure', 'Exposition constatée'), text('tests', 'Tests effectués et résultats'), choice('decision', 'Décision', ('review', 'À examiner'), ('approved', 'Approuver'), ('deferred', 'Différer')), reason()],
               'Documenter les tests et la décision sur une mise à jour.', 'Évaluation ou approbation enregistrée.', limitations='Réauthentification récente requise. L’approbateur doit être distinct de l’évaluateur ; aucun déploiement n’est simulé comme réussi.'),
        action('deletion.request', 'Demander la suppression de son compte', ['user'],
               [reason()], 'Créer une demande de suppression du compte connecté.', 'Demande visible par la sécurité, sans effacement immédiat.', limitations='Réauthentification récente requise. Le traitement respecte les contraintes de conservation.'),
        action('deletion.review', 'Examiner une demande de suppression', ['security'],
               [reference('id', 'Demande de suppression', 'deletions', display='status'), reason()],
               'Prendre en charge une demande encore non traitée.', 'Travail de suppression préparé pour l’opérateur.', limitations='Réauthentification récente requise. Aucune suppression ou preuve d’exécution n’est fabriquée.'),
        action('access.check', 'Contrôler les accès expirés', ['security'], [],
               'Vérifier les états des partages et diagnostics en base.', 'Résultat du contrôle applicatif enregistré.', limitations='Ce contrôle ne teste ni le pare-feu ni le broker ni une restauration.'),
        action('export.personal', 'Télécharger ses mesures', ['user'],
               [date_field('start', 'Début de période'), date_field('end', 'Fin de période')],
               'Exporter les mesures personnelles sur une période choisie.', 'Fichier JSON téléchargé dans la fenêtre authentifiée.',
               command=None, limitations='Période de 1 à 90 jours ; aucun transfert du fichier vers le simulateur.', method='GET', path='/api/export', fixed_payload={'kind': 'personal'}),
        action('export.prevention', 'Télécharger les recommandations', ['employer'], [],
               'Exporter les recommandations de son organisation.', 'Fichier JSON sans mesures médicales téléchargé dans la fenêtre authentifiée.',
               method='GET', path='/api/export', fixed_payload={'kind': 'prevention'}),
    ]
    workflows = [
        {'id': 'care', 'label': 'Conseil et bilan de suivi', 'description': 'Chaque étape est choisie et exécutée séparément dans le compte correspondant.', 'steps': [
            {'action_id': 'share.create', 'role': 'user', 'label': 'Autoriser le partage'},
            {'action_id': 'document.publish', 'role': 'clinician', 'label': 'Publier un conseil puis, si souhaité, un bilan'},
            {'action_id': 'notification.read', 'role': 'user', 'label': 'Consulter la notification'},
            {'action_id': 'share.revoke', 'role': 'user', 'label': 'Révoquer le partage'}]},
        {'id': 'support', 'label': 'Ticket et calibration', 'description': 'La fin matérielle reste en attente d’une preuve réelle ; aucune résolution automatique.', 'steps': [
            {'action_id': 'ticket.create', 'role': 'user', 'label': 'Ouvrir le ticket technique'},
            {'action_id': 'ticket.reply', 'role': 'support', 'label': 'Répondre au ticket attribué'},
            {'action_id': 'diagnostic.request', 'role': 'support', 'label': 'Demander un diagnostic'},
            {'action_id': 'diagnostic.approve', 'role': 'user', 'label': 'Autoriser le diagnostic'},
            {'action_id': 'device.calibrate', 'role': 'support', 'label': 'Demander la calibration'},
            {'action_id': 'ticket.checks', 'role': 'support', 'label': 'Consigner les contrôles effectivement réalisés'},
            {'action_id': 'ticket.status', 'role': 'support', 'label': 'Choisir le statut permis par les preuves'}]},
        {'id': 'prevention', 'label': 'Recommandation et avancement', 'description': 'Les recommandations restent organisationnelles, sans données médicales individuelles.', 'steps': [
            {'action_id': 'recommendation.publish', 'role': 'clinician', 'label': 'Publier une recommandation'},
            {'action_id': 'recommendation.status', 'role': 'employer', 'label': 'Choisir l’avancement'},
            {'action_id': 'recommendation.revise', 'role': 'clinician', 'label': 'Corriger si nécessaire'},
            {'action_id': 'export.prevention', 'role': 'employer', 'label': 'Télécharger le récapitulatif'}]},
        {'id': 'security', 'label': 'Signalement et incident', 'description': 'Un signalement synthétique teste le suivi ; il ne constitue pas une attaque réseau.', 'steps': [
            {'action_id': 'security.report', 'role': 'support', 'label': 'Signaler une anomalie technique'},
            {'action_id': 'incident.qualify', 'role': 'security', 'label': 'Qualifier le signalement'},
            {'action_id': 'incident.action', 'role': 'security', 'label': 'Consigner le traitement effectué'},
            {'action_id': 'incident.close', 'role': 'security', 'label': 'Clôturer avec une vérification'}]},
        {'id': 'update', 'label': 'Évaluation et demande de mise à jour', 'description': 'Changer d’administrateur pour l’approbation. L’installation doit être vérifiée par l’adaptateur.', 'steps': [
            {'action_id': 'patch.evaluate', 'role': 'security', 'label': 'Évaluer les résultats des tests'},
            {'action_id': 'patch.evaluate', 'role': 'security', 'label': 'Faire approuver par un second administrateur'},
            {'action_id': 'device.update', 'role': 'support', 'label': 'Demander l’installation dans une intervention autorisée'}]},
    ]
    return deepcopy({'schema_version': 'skelivia.actions.v1', 'roles': [{'id': r, 'label': LABELS[r]} for r in ROLES],
                     'actions': acts, 'workflows': workflows,
                     'notice': 'Les actions modifient réellement le banc local. Elles utilisent le compte connecté et les contrôles existants. Aucune étape suivante n’est lancée automatiquement.'})


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Exporter le catalogue public sans accéder aux données du banc.')
    parser.add_argument('--export', required=True, type=Path)
    args = parser.parse_args()
    args.export.write_text(json.dumps(catalog(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
