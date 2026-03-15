"""
Mixins pour le back-office : layout Vuexy + accès réservé au staff.
"""
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from web_project import TemplateLayout


# ——— Règles de visibilité du menu ———
# Une section (ex. Produits) est visible si l'utilisateur a AU MOINS UNE des permissions
# du domaine. Les boutons/actions dans la page (ajouter, modifier, supprimer) restent
# contrôlés chacun par sa propre permission.
MENU_PERMISSION_GROUPS = {
    "index": ["accounts.view_dashboard"],
    "product-list": [
        "catalog.view_product",
        "catalog.add_product",
        "catalog.change_product",
        "catalog.delete_product",
        "catalog.add_stockmovement",
        "catalog.change_stockmovement",
        "catalog.delete_stockmovement",
    ],
    "client-list": [
        "clients.view_clientprofile",
        "clients.add_clientprofile",
        "clients.change_clientprofile",
        "clients.delete_clientprofile",
    ],
    "quote-list": [
        "quotes.view_quoterequest",
        "quotes.change_quoterequest",
        "quotes.delete_quoterequest",
    ],
    "historique": ["catalog.view_stockmovement"],
}

MENU_HEADER_ITEMS = {
    "Catalogue": ["product-list", "client-list", "quote-list"],
    "Activité": ["historique"],
    "Administration": ["user-list", "role-list"],
}


def _user_has_any_menu_permission(user, perms):
    """True si l'utilisateur a au moins une des permissions (liste vide = False)."""
    return bool(perms) and any(user.has_perm(p) for p in perms)


class StaffRequiredMixin:
    """Vue accessible uniquement aux utilisateurs authentifiés et staff."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("front:login"), "next")
        if not request.user.is_staff:
            return redirect("front:index")
        return super().dispatch(request, *args, **kwargs)


class SuperuserRequiredMixin(StaffRequiredMixin):
    """Vue réservée aux superutilisateurs (ex. gestion utilisateurs et rôles)."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect_to_login(request.get_full_path(), reverse("front:login"), "next")
        if not request.user.is_staff:
            return redirect("front:index")
        return super().dispatch(request, *args, **kwargs)


class AnyPermissionRequiredMixin(AccessMixin):
    """
    Accès autorisé si l'utilisateur a AU MOINS UNE des permissions (permission_required).
    À combiner avec StaffRequiredMixin. Utilisé pour les pages liste : si l'utilisateur
    a par ex. seulement « Ajouter un produit », la section Produits reste visible et
    il peut ouvrir la page (les boutons sont ensuite gérés par leurs permissions).
    """
    permission_required = None  # liste de permissions (au moins une requise)

    def get_permission_required(self):
        return self.permission_required or []

    def has_permission(self):
        perms = self.get_permission_required()
        if not perms:
            return True
        return any(self.request.user.has_perm(p) for p in perms)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.has_permission():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class GestionLayoutMixin:
    """Injecte le layout Vuexy (menu, navbar) dans le contexte."""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = TemplateLayout.init(self, context)
        # Filtrer le menu : une section n'est masquée que si l'utilisateur n'a AUCUNE
        # des permissions du domaine (ex. Produits visible si au moins view/add/change/delete/manage_stock).
        if "menu_data" in context and hasattr(self.request, "user"):
            menu = context["menu_data"].get("menu", [])
            user = self.request.user
            new_menu = []
            for item in menu:
                slug = item.get("slug")
                header = item.get("menu_header")
                if header:
                    if header == "Administration":
                        if not user.is_superuser:
                            continue
                    elif header == "Activité":
                        if not _user_has_any_menu_permission(user, MENU_PERMISSION_GROUPS.get("historique", [])):
                            continue
                    elif header == "Catalogue":
                        catalog_slugs = MENU_HEADER_ITEMS.get("Catalogue", [])
                        if not any(
                            _user_has_any_menu_permission(user, MENU_PERMISSION_GROUPS.get(s, []))
                            for s in catalog_slugs
                        ):
                            continue
                elif slug:
                    if slug in ("user-list", "role-list"):
                        if not user.is_superuser:
                            continue
                    elif slug in MENU_PERMISSION_GROUPS:
                        if not _user_has_any_menu_permission(user, MENU_PERMISSION_GROUPS[slug]):
                            continue
                new_menu.append(item)
            context["menu_data"] = {"menu": new_menu}
        return context
