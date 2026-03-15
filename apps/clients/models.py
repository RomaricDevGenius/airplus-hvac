"""
Profil client : lié à un User (OneToOne).
Un client peut être créé par l'admin (mot de passe par défaut) ou s'inscrire lui-même.
"""
from django.conf import settings
from django.db import models


class ClientProfile(models.Model):
    """
    Profil client. user.is_staff=False pour les clients du site.
    L'admin peut créer un User + ClientProfile avec mot de passe par défaut ;
    le client peut le modifier à la première connexion.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
        verbose_name="Compte utilisateur",
    )
    company_name = models.CharField("Raison sociale / Entreprise", max_length=255, blank=True)
    phone = models.CharField("Téléphone", max_length=32, blank=True)
    address = models.TextField("Adresse", blank=True)
    # Indique si le mot de passe a été changé depuis la création par l'admin
    password_changed = models.BooleanField("Mot de passe modifié par le client", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients_clientprofile"
        verbose_name = "Profil client"
        verbose_name_plural = "Profils clients"

    def __str__(self):
        return self.user.get_full_name() or self.user.username or str(self.user.pk)
