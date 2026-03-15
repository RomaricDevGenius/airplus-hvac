"""
Produits et mouvements de stock.
Champs produit : référence, désignation, quantité, observation, prix unitaire, image.
Mouvements de stock pour l'historique (sortie/entrée avec note).
"""
from django.conf import settings
from django.db import models


class Product(models.Model):
    """Produit : référence, désignation, quantité, observation, prix unitaire, image."""
    reference = models.CharField("Référence", max_length=64, unique=True, db_index=True)
    designation = models.CharField("Désignation", max_length=255)
    quantity = models.PositiveIntegerField("Quantité en stock", default=0)
    observation = models.TextField("Observation", blank=True)
    unit_price = models.DecimalField(
        "Prix unitaire",
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Prix unitaire (devise locale)",
    )
    image = models.ImageField(
        "Image du produit",
        upload_to="catalog/products/%Y/%m/",
        blank=True,
        null=True,
    )
    # Seuil d'alerte : si quantity <= alert_threshold, envoi email admin
    alert_threshold = models.PositiveIntegerField(
        "Seuil d'alerte stock",
        default=5,
        help_text="Alerte email si stock <= ce seuil",
    )
    is_visible = models.BooleanField(
        "Visible sur le site client",
        default=True,
        help_text="Si coché, le produit apparaît sur le site vitrine.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_product"
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ("reference",)

    def __str__(self):
        return f"{self.reference} – {self.designation}"

    @property
    def is_low_stock(self):
        return self.quantity <= self.alert_threshold


class StockMovement(models.Model):
    """
    Mouvement de stock : entrée ou sortie avec note (pour traçabilité).
    Utilisé par le bouton "Sortie rapide" / "Ajuster stock" (note + quantité).
    """
    class MovementType(models.TextChoices):
        IN = "in", "Entrée"
        OUT = "out", "Sortie"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_movements",
        verbose_name="Produit",
    )
    movement_type = models.CharField(
        max_length=3,
        choices=MovementType.choices,
    )
    quantity = models.PositiveIntegerField("Quantité")
    note = models.CharField(
        "Motif / note",
        max_length=255,
        blank=True,
        help_text="Ex. : Vente, Réception, Correction, etc.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_movements_created",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_stockmovement"
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.product.reference} – {self.get_movement_type_display()} {self.quantity}"


class ProductImage(models.Model):
    """Images supplémentaires pour la vue 360° d'un produit."""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images_360",
        verbose_name="Produit",
    )
    image = models.ImageField(
        "Image",
        upload_to="catalog/products/360/%Y/%m/",
    )
    order = models.PositiveSmallIntegerField(
        "Ordre",
        default=0,
        help_text="Les images seront affichées dans cet ordre lors de la rotation 360°.",
    )

    class Meta:
        db_table = "catalog_productimage"
        verbose_name = "Image 360°"
        verbose_name_plural = "Images 360°"
        ordering = ("product", "order")

    def __str__(self):
        return f"{self.product.reference} – Image {self.order}"
