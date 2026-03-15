"""
Back-office AIRPLUS HVAC : tableau de bord, produits, stock, clients, devis.
Connexion dédiée /gestion/connexion/ → redirection vers le dashboard.
"""
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView, View
from django.views.generic.edit import CreateView, DeleteView, FormView, UpdateView

from django.contrib.auth.models import Group

from .forms import (
    ClientCreateForm,
    ClientUpdateForm,
    EmailAuthenticationForm,
    EmailChangeForm,
    GroupForm,
    UserCreateForm,
    UserUpdateForm,
    get_permissions_grouped,
)

from apps.catalog.models import Product, StockMovement
from apps.catalog.services import StockService
from apps.clients.models import ClientProfile
from apps.quotes.models import QuoteRequest, QuoteRequestItem

from .mixins import (
    GestionLayoutMixin,
    MENU_PERMISSION_GROUPS,
    AnyPermissionRequiredMixin,
    StaffRequiredMixin,
    SuperuserRequiredMixin,
)

User = get_user_model()


# ——— Connexion unifiée (admin + clients) ———
# Un seul formulaire pour tout le monde : staff → /gestion/, client → site.

class UnifiedLoginView(LoginView):
    """
    Connexion unique : même formulaire pour admin/personnel et clients.
    - Staff → redirection vers /gestion/
    - Client → redirection vers le site (accueil ou ?next=)
    """
    template_name = "admin/gestion/login.html"
    form_class = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if self.request.user.is_staff and next_url and next_url.startswith("/gestion/"):
            return next_url
        if not self.request.user.is_staff and next_url and (next_url.startswith("/") and not next_url.startswith("/gestion/")):
            return next_url
        if self.request.user.is_staff:
            return str(reverse_lazy("gestion:index"))
        return str(reverse_lazy("front:index"))

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_staff:
                return redirect("gestion:index")
            return redirect("front:index")
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        # Récupérer next depuis GET ou POST
        next_url = self.request.GET.get("next") or self.request.POST.get("next", "")
        next_url = next_url.strip()

        # Logique de redirection selon le type d'utilisateur
        if user.is_staff:
            # Staff : vers back-office ou next si c'est une URL /gestion/
            if next_url and next_url.startswith("/gestion/"):
                return redirect(next_url)
            return redirect("gestion:index")
        else:
            # Client : vers site ou next si ce n'est pas une URL back-office
            if next_url and next_url.startswith("/") and not next_url.startswith("/gestion/"):
                return redirect(next_url)
            return redirect("front:index")


def gestion_logout_view(request):
    """Déconnexion (back-office ou site) → formulaire de connexion unique."""
    logout(request)
    return redirect("front:login")


# ——— Dashboard ———

class DashboardView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, TemplateView):
    permission_required = "accounts.view_dashboard"
    template_name = "admin/gestion/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products_count"] = Product.objects.count()
        context["products_low_stock"] = Product.objects.filter(quantity__lte=F("alert_threshold")).count()
        context["quotes_pending"] = QuoteRequest.objects.filter(status="pending").count()
        context["clients_count"] = ClientProfile.objects.count()
        context["recent_quotes"] = QuoteRequest.objects.select_related("client").order_by("-created_at")[:5]
        context["low_stock_products"] = Product.objects.filter(quantity__lte=F("alert_threshold")).order_by("quantity")[:5]
        return context


# ——— Produits ———

class ProductListView(StaffRequiredMixin, AnyPermissionRequiredMixin, GestionLayoutMixin, ListView):
    permission_required = MENU_PERMISSION_GROUPS["product-list"]
    model = Product
    template_name = "admin/gestion/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_template_names(self):
        return ["admin/gestion/product_list.html"]

    def get_queryset(self):
        qs = Product.objects.all().order_by("reference")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) | Q(designation__icontains=q)
            )
        return qs


class ProductCreateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, CreateView):
    permission_required = "catalog.add_product"
    model = Product
    template_name = "admin/gestion/product_form.html"
    fields = (
        "reference", "designation", "quantity", "observation",
        "unit_price", "image", "alert_threshold", "is_visible",
    )
    success_url = reverse_lazy("gestion:product-list")

    def form_valid(self, form):
        messages.success(self.request, "Produit créé.")
        return super().form_valid(form)


class ProductUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, UpdateView):
    permission_required = "catalog.change_product"
    model = Product
    template_name = "admin/gestion/product_form.html"
    context_object_name = "product"
    fields = (
        "reference", "designation", "quantity", "observation",
        "unit_price", "image", "alert_threshold", "is_visible",
    )
    success_url = reverse_lazy("gestion:product-list")

    def form_valid(self, form):
        messages.success(self.request, "Produit mis à jour.")
        return super().form_valid(form)


class ProductDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DeleteView):
    permission_required = "catalog.delete_product"
    model = Product
    template_name = "admin/gestion/product_confirm_delete.html"
    context_object_name = "product"
    success_url = reverse_lazy("gestion:product-list")

    def form_valid(self, form):
        messages.success(self.request, "Produit supprimé.")
        return super().form_valid(form)


class StockMovementView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, TemplateView):
    permission_required = "catalog.add_stockmovement"
    """Formulaire mouvement de stock (entrée/sortie) pour un produit."""
    template_name = "admin/gestion/stock_movement.html"

    def get(self, request, product_id, *args, **kwargs):
        self._product = get_object_or_404(Product, pk=product_id)
        return super().get(request, *args, **kwargs)

    def post(self, request, product_id, *args, **kwargs):
        self._product = get_object_or_404(Product, pk=product_id)
        movement_type = request.POST.get("movement_type")
        quantity_str = request.POST.get("quantity", "0").strip()
        note = request.POST.get("note", "").strip()
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                messages.warning(request, "La quantité doit être strictement positive.")
            else:
                StockService.apply_movement(product_id, movement_type, quantity, note, request.user)
                messages.success(request, "Mouvement enregistré.")
                return redirect("gestion:product-list")
        except ValueError as e:
            messages.error(request, str(e))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = getattr(self, "_product", None)
        return context


# ——— Clients ———

class ClientListView(StaffRequiredMixin, AnyPermissionRequiredMixin, GestionLayoutMixin, ListView):
    permission_required = MENU_PERMISSION_GROUPS["client-list"]
    model = ClientProfile
    template_name = "admin/gestion/client_list.html"
    context_object_name = "clients"
    paginate_by = 20

    def get_queryset(self):
        return ClientProfile.objects.select_related("user").order_by("user__username")


class ClientDetailView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DetailView):
    permission_required = "clients.view_clientprofile"
    model = ClientProfile
    template_name = "admin/gestion/client_detail.html"
    context_object_name = "client"


class ClientCreateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, FormView):
    permission_required = "clients.add_clientprofile"
    """Création d'un client par l'admin (User + ClientProfile)."""
    form_class = ClientCreateForm
    template_name = "admin/gestion/client_form.html"
    success_url = reverse_lazy("gestion:client-list")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Client créé. Il peut se connecter au site avec son email et le mot de passe défini.")
        return redirect(self.success_url)


class ClientUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, FormView):
    permission_required = "clients.change_clientprofile"
    model = ClientProfile
    form_class = ClientUpdateForm
    template_name = "admin/gestion/client_form.html"
    context_object_name = "client"
    success_url = reverse_lazy("gestion:client-list")

    def get_object(self):
        return get_object_or_404(ClientProfile, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["client_profile"] = self.get_object()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["client"] = self.get_object()
        context["is_edit"] = True
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Client mis à jour.")
        return redirect(self.success_url)


class ClientDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DeleteView):
    permission_required = "clients.delete_clientprofile"
    model = ClientProfile
    template_name = "admin/gestion/client_confirm_delete.html"
    context_object_name = "client"
    success_url = reverse_lazy("gestion:client-list")

    def form_valid(self, form):
        obj = self.get_object()
        user = obj.user
        obj.delete()
        user.delete()
        messages.success(self.request, "Client supprimé.")
        return redirect(self.success_url)


# ——— Demandes de devis ———

class QuoteRequestListView(StaffRequiredMixin, AnyPermissionRequiredMixin, GestionLayoutMixin, ListView):
    permission_required = MENU_PERMISSION_GROUPS["quote-list"]
    model = QuoteRequest
    template_name = "admin/gestion/quote_list.html"
    context_object_name = "quotes"
    paginate_by = 20

    def get_queryset(self):
        return QuoteRequest.objects.select_related("client").prefetch_related("items").order_by("-created_at")


class QuoteRequestDetailView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DetailView):
    permission_required = "quotes.view_quoterequest"
    model = QuoteRequest
    template_name = "admin/gestion/quote_detail.html"
    context_object_name = "quote"


class QuoteRequestProcessView(StaffRequiredMixin, PermissionRequiredMixin, View):
    """Change le statut d'une demande de devis à 'Traité'."""
    permission_required = "quotes.change_quoterequest"

    def post(self, request, pk):
        quote = get_object_or_404(QuoteRequest, pk=pk)
        quote.status = QuoteRequest.Status.PROCESSED
        quote.save(update_fields=["status", "updated_at"])
        messages.success(request, f"La demande a été marquée comme traitée.")
        return redirect("gestion:quote-list")


class QuoteRequestUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, UpdateView):
    """Modification du statut et des notes admin d'une demande de devis."""
    permission_required = "quotes.change_quoterequest"
    model = QuoteRequest
    template_name = "admin/gestion/quote_form.html"
    context_object_name = "quote"
    fields = ("status", "admin_notes")
    success_url = reverse_lazy("gestion:quote-list")

    def form_valid(self, form):
        messages.success(self.request, "La demande de devis a été mise à jour.")
        return super().form_valid(form)


class QuoteRequestDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DeleteView):
    """Suppression d'une demande de devis."""
    permission_required = "quotes.delete_quoterequest"
    model = QuoteRequest
    template_name = "admin/gestion/quote_confirm_delete.html"
    context_object_name = "quote"
    success_url = reverse_lazy("gestion:quote-list")

    def form_valid(self, form):
        messages.success(self.request, "La demande de devis a été supprimée.")
        return super().form_valid(form)


# ——— Profil admin ———

class ProfileView(StaffRequiredMixin, GestionLayoutMixin, TemplateView):
    """Page profil de l'administrateur connecté (affichage pro, modification email)."""
    template_name = "admin/gestion/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["admin_user"] = self.request.user
        context["email_form"] = EmailChangeForm(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        """Traitement du formulaire de changement d'email."""
        form = EmailChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre adresse email a été mise à jour. Utilisez-la pour vous connecter.")
            return redirect("gestion:profile")
        context = self.get_context_data()
        context["email_form"] = form
        return render(request, self.template_name, context)


class GestionPasswordChangeView(StaffRequiredMixin, GestionLayoutMixin, PasswordChangeView):
    """Changement de mot de passe (back-office)."""
    template_name = "admin/gestion/password_change.html"
    success_url = reverse_lazy("gestion:profile")

    def form_valid(self, form):
        messages.success(self.request, "Votre mot de passe a été modifié avec succès.")
        return super().form_valid(form)


# ——— Utilisateurs (superuser) ———

class UserListView(SuperuserRequiredMixin, GestionLayoutMixin, ListView):
    """Liste du personnel (utilisateurs back-office). Les clients sont gérés dans Catalogue > Clients."""
    model = User
    template_name = "admin/gestion/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        return User.objects.filter(is_staff=True).order_by("email").prefetch_related("groups")


class UserCreateView(SuperuserRequiredMixin, GestionLayoutMixin, CreateView):
    """Création d'un utilisateur (connexion par email)."""
    model = User
    form_class = UserCreateForm
    template_name = "admin/gestion/user_form.html"
    success_url = reverse_lazy("gestion:user-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["all_groups"] = Group.objects.order_by("name")
        if self.request.method == "POST" and "groups" in self.request.POST:
            context["selected_group_ids"] = [int(x) for x in self.request.POST.getlist("groups") if x.isdigit()]
        else:
            context["selected_group_ids"] = []
        return context

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur créé. Il peut se connecter avec son email et le mot de passe défini.")
        return super().form_valid(form)


class UserUpdateView(SuperuserRequiredMixin, GestionLayoutMixin, UpdateView):
    """Édition d'un utilisateur."""
    model = User
    form_class = UserUpdateForm
    template_name = "admin/gestion/user_form.html"
    context_object_name = "user_obj"
    success_url = reverse_lazy("gestion:user-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["all_groups"] = Group.objects.order_by("name")
        if self.request.method == "POST" and "groups" in self.request.POST:
            context["selected_group_ids"] = [int(x) for x in self.request.POST.getlist("groups") if x.isdigit()]
        else:
            context["selected_group_ids"] = list(self.object.groups.values_list("pk", flat=True)) if self.object.pk else []
        return context

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur mis à jour.")
        return super().form_valid(form)


class UserDeleteView(SuperuserRequiredMixin, GestionLayoutMixin, DeleteView):
    """Suppression d'un utilisateur."""
    model = User
    template_name = "admin/gestion/user_confirm_delete.html"
    context_object_name = "user_obj"
    success_url = reverse_lazy("gestion:user-list")

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur supprimé.")
        return super().form_valid(form)


# ——— Rôles (Group, superuser) ———

class RoleListView(SuperuserRequiredMixin, GestionLayoutMixin, ListView):
    """Liste des rôles (groupes Django)."""
    model = Group
    template_name = "admin/gestion/role_list.html"
    context_object_name = "roles"
    paginate_by = 20

    def get_queryset(self):
        return Group.objects.prefetch_related("permissions").order_by("name")


class RoleDetailView(SuperuserRequiredMixin, GestionLayoutMixin, DetailView):
    """Détail d'un rôle : permissions attribuées et personnel avec ce rôle."""
    model = Group
    template_name = "admin/gestion/role_detail.html"
    context_object_name = "role"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .forms import get_permission_label, PERMISSION_SECTION_LABELS
        role_perms = self.object.permissions.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        grouped = {}
        for p in role_perms:
            section = PERMISSION_SECTION_LABELS.get(p.content_type.app_label, p.content_type.app_label)
            grouped.setdefault(section, []).append(get_permission_label(p))
        context["permissions_grouped"] = list(grouped.items())
        context["users_with_role"] = self.object.user_set.filter(is_staff=True).order_by("email")
        return context


class RoleCreateView(SuperuserRequiredMixin, GestionLayoutMixin, CreateView):
    """Création d'un rôle."""
    model = Group
    form_class = GroupForm
    template_name = "admin/gestion/role_form.html"
    success_url = reverse_lazy("gestion:role-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["permissions_grouped"] = get_permissions_grouped()
        if self.request.method == "POST" and "permissions" in self.request.POST:
            context["selected_permission_ids"] = [int(x) for x in self.request.POST.getlist("permissions") if x.isdigit()]
        else:
            context["selected_permission_ids"] = []
        return context

    def form_valid(self, form):
        messages.success(self.request, "Rôle créé.")
        return super().form_valid(form)


class RoleUpdateView(SuperuserRequiredMixin, GestionLayoutMixin, UpdateView):
    """Édition d'un rôle."""
    model = Group
    form_class = GroupForm
    template_name = "admin/gestion/role_form.html"
    context_object_name = "role"
    success_url = reverse_lazy("gestion:role-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["permissions_grouped"] = get_permissions_grouped()
        if self.request.method == "POST" and "permissions" in self.request.POST:
            context["selected_permission_ids"] = [int(x) for x in self.request.POST.getlist("permissions") if x.isdigit()]
        else:
            context["selected_permission_ids"] = list(self.object.permissions.values_list("pk", flat=True)) if self.object.pk else []
        return context

    def form_valid(self, form):
        messages.success(self.request, "Rôle mis à jour.")
        return super().form_valid(form)


class RoleDeleteView(SuperuserRequiredMixin, GestionLayoutMixin, DeleteView):
    """Suppression d'un rôle."""
    model = Group
    template_name = "admin/gestion/role_confirm_delete.html"
    context_object_name = "role"
    success_url = reverse_lazy("gestion:role-list")

    def form_valid(self, form):
        messages.success(self.request, "Rôle supprimé.")
        return super().form_valid(form)


# ——— Notifications ———

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required


@login_required
@require_POST
def notification_mark_read(request, pk):
    """Marque une notification comme lue (AJAX)."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False}, status=403)
    from apps.accounts.models import Notification
    try:
        notif = Notification.objects.get(pk=pk)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
    except Notification.DoesNotExist:
        pass
    return JsonResponse({"ok": True})


@login_required
@require_POST
def notification_mark_all_read(request):
    """Marque toutes les notifications non lues comme lues (AJAX)."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False}, status=403)
    from apps.accounts.models import Notification
    Notification.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({"ok": True})

# ——— Historique ———

class HistoriqueView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, ListView):
    """Historique des mouvements de stock (visible si permission « Voir l'historique »)."""
    permission_required = "catalog.view_stockmovement"
    raise_exception = True
    model = StockMovement
    template_name = "admin/gestion/historique.html"
    context_object_name = "movements"
    paginate_by = 25

    def get_queryset(self):
        return StockMovement.objects.select_related("product", "created_by").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.quotes.models import QuoteRequest
        context["recent_quotes"] = QuoteRequest.objects.select_related("client").order_by("-created_at")[:10]
        return context
