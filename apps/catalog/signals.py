"""
Signals catalogue : alerte stock après modification d'un produit.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Product
from .services import send_stock_alert_if_needed


@receiver(post_save, sender=Product)
def product_post_save(sender, instance, created, **kwargs):
    """Après sauvegarde d'un produit, envoi alerte email si stock bas."""
    send_stock_alert_if_needed(instance)
