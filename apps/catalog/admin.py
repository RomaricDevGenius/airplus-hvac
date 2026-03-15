from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Product, ProductImage, StockMovement
from .services import StockService

User = get_user_model()


class StockMovementFormAdmin(admin.ModelAdmin):
    """Formulaire dédié mouvement de stock (sortie / entrée) sans modifier le produit."""

    def get_movement_form_view(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        if request.method == "POST":
            movement_type = request.POST.get("movement_type")
            quantity_str = request.POST.get("quantity", "0").strip()
            note = request.POST.get("note", "").strip()
            try:
                quantity = int(quantity_str)
                if quantity <= 0:
                    self.message_user(request, _("La quantité doit être strictement positive."), level=messages.WARNING)
                else:
                    StockService.apply_movement(product_id, movement_type, quantity, note, request.user)
                    self.message_user(request, _("Mouvement enregistré avec succès."))
                    return redirect("admin:catalog_product_changelist")
            except ValueError as e:
                self.message_user(request, str(e), level=messages.ERROR)
        return render(
            request,
            "admin/catalog/stock_movement_form.html",
            {
                "product": product,
                "opts": self.model._meta,
                "title": _("Mouvement de stock – %s") % product.reference,
            },
        )


@admin.register(Product)
class ProductAdmin(StockMovementFormAdmin, admin.ModelAdmin):
    list_display = ("reference", "designation", "quantity", "unit_price", "is_visible", "is_low_stock", "mouvement_stock_link")
    list_filter = ("is_visible",)
    search_fields = ("reference", "designation")
    list_editable = ("is_visible",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [type("ProductImageInline", (admin.TabularInline,), {
        "model": ProductImage,
        "extra": 3,
        "fields": ("image", "order"),
        "verbose_name": "Image 360°",
        "verbose_name_plural": "Images 360° (glisser-déposer dans l'ordre de rotation)",
    })]

    def mouvement_stock_link(self, obj):
        return format_html(
            '<a class="button" href="{}">Sortie / Ajuster stock</a>',
            f"/admin/catalog/product/{obj.pk}/stock-movement/",
        )

    mouvement_stock_link.short_description = _("Mouvement stock")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<int:product_id>/stock-movement/", self.admin_site.admin_view(self.get_movement_form_view), name="catalog_product_stock_movement"),
        ]
        return custom + urls


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity", "note", "created_by", "created_at")
    list_filter = ("movement_type", "created_at")
    search_fields = ("product__reference", "note")
    readonly_fields = ("created_at",)
