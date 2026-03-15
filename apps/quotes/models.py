"""
Demande de devis : le client (authentifié) remplit un formulaire,
envoi par email à l'admin pour réponse.
"""
from django.conf import settings
from django.db import models


class QuoteRequest(models.Model):
    """Demande de devis envoyée par un client (connecté)."""
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PROCESSED = "processed", "Traité"
        SENT = "sent", "Devis envoyé"
        CLOSED = "closed", "Clôturé"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quote_requests",
        verbose_name="Client",
    )
    subject = models.CharField("Objet de la demande", max_length=255)
    message = models.TextField("Message / détails de la demande")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_notes = models.TextField("Notes admin (interne)", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quotes_quoterequest"
        verbose_name = "Demande de devis"
        verbose_name_plural = "Demandes de devis"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.subject} – {self.client.get_full_name() or self.client.username}"


class QuoteRequestItem(models.Model):
    """Ligne de demande : produit + quantité (optionnel, pour détail)."""
    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Demande de devis",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="quote_request_items",
        verbose_name="Produit",
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField("Quantité demandée", default=1)
    note = models.CharField("Note", max_length=255, blank=True)

    class Meta:
        db_table = "quotes_quoterequestitem"
        verbose_name = "Ligne de demande"
        verbose_name_plural = "Lignes de demande"
