"""
Modèle utilisateur personnalisé.
Les rôles et permissions utilisent les Group et Permission de Django :
- Group = rôle (ex. "Gestionnaire stock", "Vendeur")
- Permission = permission (créée dans catalog, clients, quotes)
L'admin attribue des permissions aux groupes, puis assigne les groupes aux utilisateurs.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Utilisateur du système. Peut être staff (accès back-office) et/ou client (profil Client).
    Les rôles sont gérés via user.groups ; les permissions via user.user_permissions
    et les permissions des groupes.
    """
    class Meta:
        db_table = "accounts_user"
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        permissions = [
            ("view_dashboard", "Peut voir le tableau de bord"),
        ]


class Notification(models.Model):
    """Notification back-office : alerte stock bas ou nouvelle demande de devis."""

    STOCK_ALERT = "stock_alert"
    NEW_QUOTE = "new_quote"
    TYPE_CHOICES = [
        (STOCK_ALERT, "Alerte stock"),
        (NEW_QUOTE, "Nouveau devis"),
    ]

    notif_type = models.CharField("Type", max_length=20, choices=TYPE_CHOICES)
    title = models.CharField("Titre", max_length=255)
    message = models.TextField("Message")
    link = models.CharField("Lien", max_length=500, blank=True)
    is_read = models.BooleanField("Lu", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_notification"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
