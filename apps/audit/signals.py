"""
Journalisation de l'authentification : connexions, déconnexions et échecs.

Pourquoi des signaux plutôt qu'une surcharge des vues de connexion ?
- Le projet possède une connexion unifiée (back-office ET site public) mais
  `django.contrib.auth.login()` est aussi appelé ailleurs (inscription,
  administration Django). Les signaux natifs couvrent TOUS ces chemins d'un
  coup, sans modifier une seule vue — donc sans rien casser côté métier.
- Aucun couplage : `apps.front` et `apps.sample` restent inchangés.

⚠️ CONFIDENTIALITÉ — le piège de `user_login_failed`
Ce signal transporte le dictionnaire `credentials`, qui contient le mot de
passe saisi par le visiteur. On n'en extrait QUE l'identifiant tenté ; le
dictionnaire n'est jamais transmis tel quel au journal. Voir
`extract_identifier()` : la liste des clés lues est fermée (liste blanche),
tout le reste est ignoré par construction.

Les récepteurs portent un `dispatch_uid` : même si le module était importé
deux fois, aucune entrée ne serait dupliquée.
"""
import logging

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

logger = logging.getLogger("audit")

# Liste BLANCHE des clés de `credentials` susceptibles de porter l'identifiant
# saisi. Toute autre clé (password, password1, token...) est ignorée : c'est
# une liste blanche justement pour qu'aucun secret ne puisse entrer par erreur.
IDENTIFIER_KEYS = ("username", "email", "identifiant", "login")

# Longueur alignée sur AuditLog.actor_label.
MAX_IDENTIFIER = 255


def extract_identifier(credentials):
    """
    Identifiant tenté lors d'un échec de connexion, extrait de `credentials`.

    Ne renvoie JAMAIS autre chose qu'une valeur issue de IDENTIFIER_KEYS :
    le mot de passe présent dans le dictionnaire n'est jamais lu.
    """
    if not isinstance(credentials, dict):
        return ""
    for cle in IDENTIFIER_KEYS:
        valeur = credentials.get(cle)
        if valeur:
            return str(valeur)[:MAX_IDENTIFIER]
    return ""


@receiver(user_logged_in, dispatch_uid="audit_user_logged_in")
def audit_user_logged_in(sender, request=None, user=None, **kwargs):
    """Connexion réussie (back-office ou site public)."""
    try:
        from .services import log_login

        log_login(user, request=request)
    except Exception:  # noqa: BLE001 - l'audit ne doit jamais bloquer une connexion
        logger.exception("audit : connexion non journalisée")


@receiver(user_logged_out, dispatch_uid="audit_user_logged_out")
def audit_user_logged_out(sender, request=None, user=None, **kwargs):
    """
    Déconnexion. Django émet aussi ce signal pour un visiteur anonyme
    (`user=None`) : dans ce cas il n'y a rien d'intéressant à tracer.
    """
    try:
        if user is None or not getattr(user, "pk", None):
            return
        from .services import log_logout

        log_logout(user, request=request)
    except Exception:  # noqa: BLE001
        logger.exception("audit : déconnexion non journalisée")


@receiver(user_login_failed, dispatch_uid="audit_user_login_failed")
def audit_user_login_failed(sender, credentials=None, request=None, **kwargs):
    """
    Échec de connexion. Aucun utilisateur n'est authentifié : seul l'identifiant
    tenté est conservé (dans `actor_label` et dans `extra`).

    Le mot de passe présent dans `credentials` n'est ni lu, ni transmis.
    """
    try:
        from .services import log_login_failed

        log_login_failed(extract_identifier(credentials), request=request)
    except Exception:  # noqa: BLE001
        logger.exception("audit : échec de connexion non journalisé")
