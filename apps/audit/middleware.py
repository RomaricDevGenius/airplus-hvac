"""
Middleware « contexte d'audit ».

Objectif : rendre la requête HTTP courante (et donc l'utilisateur connecté,
l'IP et le user-agent) accessible depuis du code qui n'a pas `request` sous la
main — typiquement un signal `post_save` / `post_delete`.

Fonctionnement : une variable thread-local. Chaque thread de Passenger/mod_wsgi
possède sa propre copie ; la variable est TOUJOURS nettoyée en fin de requête
(bloc `finally`) pour éviter toute fuite d'un utilisateur vers la requête
suivante servie par le même thread.

Position dans MIDDLEWARE : après `AuthenticationMiddleware`, car on s'appuie
sur `request.user`.
"""
import threading

_local = threading.local()


def get_current_request():
    """Requête HTTP en cours de traitement dans ce thread, ou None (tâche hors requête)."""
    return getattr(_local, "request", None)


def get_current_user():
    """
    Utilisateur authentifié de la requête courante, ou None.
    Renvoie None pour un visiteur anonyme (AnonymousUser n'est pas persistable en FK).
    """
    request = get_current_request()
    user = getattr(request, "user", None) if request is not None else None
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


class AuditContextMiddleware:
    """Expose la requête courante en thread-local pendant toute sa durée de vie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            # Nettoyage systématique, y compris si la vue lève une exception.
            _local.request = None
