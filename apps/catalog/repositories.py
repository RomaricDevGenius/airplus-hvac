"""
Repository Catalog : couche d'accès aux données Produit et StockMovement.
Pattern Repository pour une architecture scalable et testable.
"""
from django.db import transaction, models as db_models

from .models import Product, StockMovement


class ProductRepository:
    """Accès lecture/écriture aux produits."""

    @staticmethod
    def get_all_visible():
        return Product.objects.filter(is_visible=True).order_by("reference")

    @staticmethod
    def get_all():
        return Product.objects.all().order_by("reference")

    @staticmethod
    def get_by_id(pk):
        return Product.objects.filter(pk=pk).first()

    @staticmethod
    def get_by_reference(reference):
        return Product.objects.filter(reference=reference).first()

    @staticmethod
    def get_low_stock():
        """Produits dont la quantité <= seuil d'alerte."""
        return Product.objects.filter(
            quantity__lte=db_models.F("alert_threshold"),
            is_visible=True,
        ).order_by("quantity")

    @staticmethod
    def create(**kwargs):
        return Product.objects.create(**kwargs)

    @staticmethod
    def update(instance, **kwargs):
        for key, value in kwargs.items():
            setattr(instance, key, value)
        instance.save()
        return instance

    @staticmethod
    def delete(instance):
        instance.delete()


class StockMovementRepository:
    """Accès aux mouvements de stock."""

    @staticmethod
    def get_for_product(product_id):
        return StockMovement.objects.filter(product_id=product_id).order_by("-created_at")[:50]

    @staticmethod
    def create(product_id, movement_type, quantity, note, user):
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product_id)
            if movement_type == StockMovement.MovementType.OUT:
                if product.quantity < quantity:
                    raise ValueError("Stock insuffisant.")
                product.quantity -= quantity
            else:
                product.quantity += quantity
            product.save()
            movement = StockMovement.objects.create(
                product=product,
                movement_type=movement_type,
                quantity=quantity,
                note=note or "",
                created_by=user,
            )
        return movement
