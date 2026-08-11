"""
Signals quotes : notification back-office à chaque nouvelle demande de devis.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import QuoteRequest


@receiver(post_save, sender=QuoteRequest)
def quoterequest_post_save(sender, instance, created, **kwargs):
    """Crée une notification back-office lors d'une nouvelle demande de devis."""
    if not created:
        return
    try:
        from apps.accounts.models import Notification
        client_name = instance.client.get_full_name() or instance.client.username
        Notification.objects.create(
            notif_type=Notification.NEW_QUOTE,
            title=f"Nouveau devis – {instance.subject[:60]}",
            message=f"De : {client_name} ({instance.client.email})",
            link=f"/gestion/devis/{instance.pk}/",
        )
    except Exception:
        pass
