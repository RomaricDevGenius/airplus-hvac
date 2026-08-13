"""
Journal d'audit : trace immuable des actions sensibles du back-office /gestion/
(créations, modifications, suppressions, changements de statut et de permissions)
ainsi que des connexions, déconnexions et échecs de connexion.

Principes :
- Une entrée d'audit est un FAIT HISTORIQUE : elle ne peut être ni modifiée
  ni supprimée une fois écrite (voir AuditLogImmutableError plus bas).
- Les libellés (`actor_label`, `object_repr`) sont des INSTANTANÉS pris au moment
  de l'action : si l'utilisateur ou l'objet concerné est supprimé plus tard,
  le journal reste lisible.
- La seule voie de suppression est la purge administrative explicite
  (AuditLog.purge_before / AuditLog.purge_older_than), à réserver à une
  politique de rétention décidée par le client.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AuditLogImmutableError(RuntimeError):
    """Levée dès qu'on tente de modifier ou de supprimer une entrée d'audit."""


class AuditLogQuerySet(models.QuerySet):
    """QuerySet verrouillé : `update()` et `delete()` en masse sont interdits."""

    def update(self, **kwargs):
        raise AuditLogImmutableError(
            "Le journal d'audit est immuable : mise à jour en masse interdite."
        )

    def delete(self):
        raise AuditLogImmutableError(
            "Le journal d'audit est immuable : suppression en masse interdite. "
            "Utilisez AuditLog.purge_before() pour une purge administrative."
        )

    def _purge(self):
        """
        Suppression réelle, volontairement « privée » : seul le point d'entrée
        AuditLog.purge_before() doit l'appeler.
        """
        return super().delete()


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    """Manager par défaut du journal (hérite des protections du QuerySet)."""


class AuditLog(models.Model):
    """Entrée du journal d'audit : qui a fait quoi, sur quoi, quand, et depuis où."""

    class Action(models.TextChoices):
        CREATE = "create", "Création"
        UPDATE = "update", "Modification"
        DELETE = "delete", "Suppression"
        LOGIN = "login", "Connexion"
        LOGOUT = "logout", "Déconnexion"
        LOGIN_FAILED = "login_failed", "Échec de connexion"
        STATUS_CHANGE = "status_change", "Changement de statut"
        PERMISSION_CHANGE = "permission_change", "Changement de permissions"
        EXPORT = "export", "Export de données"
        OTHER = "other", "Autre"

    action = models.CharField(
        "Action",
        max_length=32,
        choices=Action.choices,
        db_index=True,
    )

    # --- Acteur -------------------------------------------------------------
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="Auteur",
    )
    actor_label = models.CharField(
        "Auteur (libellé)",
        max_length=255,
        blank=True,
        help_text="Instantané du nom/email de l'auteur au moment de l'action : "
                  "le journal reste lisible même si le compte est supprimé.",
    )

    # --- Objet concerné -----------------------------------------------------
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Type d'objet",
    )
    object_id = models.CharField(
        "Identifiant de l'objet",
        max_length=64,
        blank=True,
        help_text="Clé primaire sous forme de texte (supporte entiers, UUID, etc.).",
    )
    object_repr = models.CharField(
        "Objet (libellé)",
        max_length=255,
        blank=True,
        help_text="Instantané de l'objet au moment de l'action (ex. « Produit REF-102 »).",
    )
    # Accès pratique à l'objet s'il existe encore (peut renvoyer None).
    content_object = GenericForeignKey("content_type", "object_id")

    # --- Détail -------------------------------------------------------------
    changes = models.JSONField(
        "Modifications",
        default=dict,
        blank=True,
        help_text='Format : {"nom_du_champ": {"avant": ..., "apres": ...}}',
    )
    extra = models.JSONField(
        "Contexte supplémentaire",
        default=dict,
        blank=True,
        help_text="Informations libres (motif, URL, identifiant tenté, etc.).",
    )

    # --- Traçabilité technique ---------------------------------------------
    ip_address = models.GenericIPAddressField("Adresse IP", null=True, blank=True)
    user_agent = models.CharField("Navigateur", max_length=400, blank=True)
    created_at = models.DateTimeField("Date", auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        verbose_name = "Entrée d'audit"
        verbose_name_plural = "Journal d'audit"
        indexes = [
            # created_at porte déjà db_index=True (index simple) : inutile de le doubler ici.
            models.Index(fields=["actor", "-created_at"], name="audit_actor_created_idx"),
            models.Index(fields=["content_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["action", "-created_at"], name="audit_action_created_idx"),
        ]

    def __str__(self):
        auteur = self.actor_label or "Système"
        cible = self.object_repr or (str(self.content_type) if self.content_type else "")
        horodatage = timezone.localtime(self.created_at).strftime("%d/%m/%Y %H:%M") if self.created_at else ""
        if cible:
            return f"{horodatage} – {auteur} : {self.get_action_display()} – {cible}"
        return f"{horodatage} – {auteur} : {self.get_action_display()}"

    # --- Immuabilité --------------------------------------------------------

    def save(self, *args, **kwargs):
        """Autorise uniquement l'insertion initiale ; toute réécriture est refusée."""
        if not self._state.adding:
            raise AuditLogImmutableError(
                "Une entrée d'audit ne peut pas être modifiée (entrée #%s)." % self.pk
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Suppression unitaire toujours refusée (voir purge_before pour la rétention)."""
        raise AuditLogImmutableError(
            "Une entrée d'audit ne peut pas être supprimée (entrée #%s). "
            "Utilisez AuditLog.purge_before() pour une purge administrative." % self.pk
        )

    # --- Purge administrative ----------------------------------------------

    @classmethod
    def purge_before(cls, cutoff):
        """
        SEUL point d'entrée autorisé pour supprimer des entrées d'audit.

        Destiné à une politique de rétention explicite (ex. « on conserve 3 ans »),
        à lancer depuis un shell Django ou une commande d'administration, jamais
        depuis une vue.

            from django.utils import timezone
            from datetime import timedelta
            from apps.audit.models import AuditLog
            AuditLog.purge_before(timezone.now() - timedelta(days=365 * 3))

        :param cutoff: datetime ; toutes les entrées STRICTEMENT antérieures sont supprimées.
        :return: nombre d'entrées supprimées.
        """
        if cutoff is None:
            raise ValueError("purge_before() exige une date de coupure explicite.")
        supprimees, _details = cls.objects.filter(created_at__lt=cutoff)._purge()
        return supprimees

    @classmethod
    def purge_older_than(cls, days):
        """Raccourci de purge_before() exprimé en nombre de jours de rétention."""
        from datetime import timedelta

        if not isinstance(days, int) or days <= 0:
            raise ValueError("purge_older_than() exige un nombre de jours entier positif.")
        return cls.purge_before(timezone.now() - timedelta(days=days))

    # --- Affichage ----------------------------------------------------------

    @property
    def changes_display(self):
        """
        Rend `changes` sous forme de liste lisible, prête pour un template :

            [{"champ": "quantity", "avant": "10", "apres": "7"}, ...]
        """
        lignes = []
        if not isinstance(self.changes, dict):
            return lignes
        for champ, valeurs in self.changes.items():
            if isinstance(valeurs, dict):
                avant = valeurs.get("avant")
                apres = valeurs.get("apres")
            else:  # tolérance : ancienne forme ou valeur brute
                avant, apres = None, valeurs
            lignes.append({
                "champ": champ,
                "avant": self._format_valeur(avant),
                "apres": self._format_valeur(apres),
            })
        return lignes

    @property
    def changes_summary(self):
        """Résumé sur une ligne : « quantity : 10 → 7 ; note : (vide) → Vente »."""
        return " ; ".join(
            f"{ligne['champ']} : {ligne['avant']} → {ligne['apres']}"
            for ligne in self.changes_display
        )

    @staticmethod
    def _format_valeur(valeur):
        """Représentation texte tolérante d'une valeur du journal."""
        if valeur is None or valeur == "":
            return "(vide)"
        if valeur is True:
            return "Oui"
        if valeur is False:
            return "Non"
        if isinstance(valeur, (list, tuple)):
            return ", ".join(str(v) for v in valeur) or "(vide)"
        return str(valeur)
