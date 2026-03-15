"""
Backend d'authentification par email pour le back-office.
Permet la connexion avec email + mot de passe (sans nom d'utilisateur).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailAuthBackend(ModelBackend):
    """
    Authentifie par email et mot de passe.
    Le champ "username" du formulaire de connexion contient l'email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        email = username.strip().lower()
        try:
            user = User.objects.filter(email__iexact=email).first()
            if user and user.check_password(password):
                return user
        except Exception:
            pass
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
