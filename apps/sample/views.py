"""
Back-office AIRPLUS HVAC : tableau de bord, produits, stock, clients, devis.
Connexion dédiée /gestion/connexion/ → redirection vers le dashboard.
"""
import logging

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
    get_permission_label,
    get_permissions_grouped,
)

from apps.audit.models import AuditLog
from apps.audit.services import (
    capture,
    diff,
    log_action,
    log_create,
    log_delete,
    log_update,
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
)

User = get_user_model()

audit_logger = logging.getLogger("audit")


# ———————————————————————————————————————————————————————————————————————————
# Journal d'audit : outillage commun aux vues du back-office
#
# Principe : ces mixins AJOUTENT de la journalisation, ils ne réécrivent aucune
# vue. Ils s'insèrent juste avant la vue générique Django dans la liste des
# classes de base, de sorte que le `form_valid()` déjà écrit dans chaque vue
# (messages, redirections) continue de fonctionner à l'identique.
#
# Règle absolue : l'audit ne doit JAMAIS faire échouer l'action métier.
# `log_action()` avale déjà ses erreurs ; tout le code de préparation ci-dessous
# (photographie d'un état, lecture d'un many-to-many) est protégé de la même
# façon.
# ———————————————————————————————————————————————————————————————————————————

def audit_permission_labels(manager):
    """
    Libellés MÉTIER des permissions d'un rôle (« Voir les produits »), et non
    les codes techniques (« catalog | produit | Can view produit »).
    `select_related` évite une requête par permission.
    """
    return [get_permission_label(p) for p in manager.select_related("content_type")]


def audit_m2m_labels(obj, field_name, labeller=None):
    """
    Liste TRIÉE et LISIBLE des objets liés par un many-to-many : « Vendeur »,
    « Voir les produits »... jamais des identifiants numériques — le journal
    est lu par un gérant, pas par un développeur.

    :param labeller: callable recevant le *manager* de relation et renvoyant
                     des libellés. Par défaut : `str()` de chaque objet lié.
    :return: liste de chaînes ; [] si l'objet n'est pas encore enregistré ou
             si la lecture échoue (jamais d'exception).
    """
    try:
        if obj is None or not getattr(obj, "pk", None):
            return []
        manager = getattr(obj, field_name, None)
        if manager is None:
            return []
        valeurs = labeller(manager) if labeller else manager.all()
        return sorted(str(valeur) for valeur in valeurs)
    except Exception:  # noqa: BLE001
        audit_logger.debug("audit : many-to-many « %s » illisible", field_name, exc_info=True)
        return []


def audit_snapshot(obj, m2m_fields=None):
    """
    Photographie complète d'un objet : champs concrets (via `capture()`, qui
    omet déjà les champs sensibles) + many-to-many rendus lisibles.
    """
    try:
        etat = capture(obj)
    except Exception:  # noqa: BLE001
        audit_logger.debug("audit : photographie impossible pour %r", type(obj), exc_info=True)
        etat = {}
    for nom, labeller in (m2m_fields or {}).items():
        etat[nom] = audit_m2m_labels(obj, nom, labeller)
    return etat


def audit_choice_labels(obj, field_name, valeurs):
    """
    Traduction lisible d'un champ à choix : {"avant": "En attente",
    "apres": "Traité"} pour un `status` valant « pending » puis « processed ».
    Renvoie None si le champ n'a pas de choix.
    """
    try:
        libelles = dict(obj._meta.get_field(field_name).choices or ())
    except Exception:  # noqa: BLE001
        return None
    if not libelles:
        return None
    return {cle: libelles.get(valeur, valeur) for cle, valeur in valeurs.items()}


def audit_emit_changes(obj, modifications, request,
                       permission_fields=(), status_fields=(), extra=None):
    """
    Écrit un diff dans le journal, en le répartissant selon la NATURE des
    champs modifiés :

    - PERMISSION_CHANGE : rôles, is_staff, is_active, permissions d'un rôle —
      les modifications les plus sensibles de l'application ;
    - STATUS_CHANGE     : champs de statut (statut d'une demande de devis) ;
    - UPDATE            : tout le reste.

    Chaque entrée n'est écrite que si son lot de champs a réellement changé :
    pas de doublon, pas de bruit.
    """
    if not modifications:
        return
    permission_fields = set(permission_fields or ())
    status_fields = set(status_fields or ())
    lots = (
        (AuditLog.Action.PERMISSION_CHANGE,
         {champ: v for champ, v in modifications.items() if champ in permission_fields}),
        (AuditLog.Action.STATUS_CHANGE,
         {champ: v for champ, v in modifications.items() if champ in status_fields}),
        (AuditLog.Action.UPDATE,
         {champ: v for champ, v in modifications.items()
          if champ not in permission_fields and champ not in status_fields}),
    )
    for action, lot in lots:
        if not lot:
            continue
        contexte = dict(extra or {})
        libelles = {}
        for champ, valeurs in lot.items():
            lisible = audit_choice_labels(obj, champ, valeurs)
            if lisible:
                libelles[champ] = lisible
        if libelles:
            contexte["libelles"] = libelles
        log_action(action, request=request, obj=obj, changes=lot, extra=contexte or None)


class AuditedViewMixin:
    """Réglages partagés par les mixins d'audit (voir ci-dessous)."""

    # {"nom_du_m2m": labeller|None} — many-to-many à photographier.
    audit_m2m_fields = {}
    # Champs dont la modification relève d'un changement de droits.
    audit_permission_fields = ()
    # Champs dont la modification relève d'un changement de statut.
    audit_status_fields = ()

    def audit_snapshot(self, obj):
        return audit_snapshot(obj, self.audit_m2m_fields)


class AuditCreateMixin(AuditedViewMixin):
    """Journalise une CRÉATION, une fois l'objet réellement enregistré."""

    def form_valid(self, form):
        response = super().form_valid(form)
        objet = getattr(self, "object", None) or getattr(form, "instance", None)
        if objet is not None and getattr(objet, "pk", None):
            log_create(objet, request=self.request,
                       extra={"valeurs": self.audit_snapshot(objet)})
        return response


class AuditUpdateMixin(AuditedViewMixin):
    """
    Journalise une MODIFICATION avec les valeurs AVANT / APRÈS.

    Difficulté résolue ici : dans une UpdateView, `self.object` porte déjà les
    valeurs du formulaire quand `form_valid()` est appelé (le formulaire est
    construit avec `instance=self.object` et modifie cette instance en place).
    Photographier à ce moment-là donnerait « après » des deux côtés et un diff
    vide. On photographie donc dans `get_object()`, appelé par `post()` AVANT
    toute construction de formulaire.

    `get_object()` peut être appelé plusieurs fois dans un même cycle
    (get_context_data, get_form_kwargs...) : le garde `is None` garantit que le
    premier instantané — le seul correct — n'est jamais écrasé.
    """

    _audit_before = None  # valeur par défaut de classe ; écrite par instance

    def get_object(self, queryset=None):
        objet = super().get_object(queryset)
        if self._audit_before is None:
            self._audit_before = self.audit_snapshot(objet)
        return objet

    def form_valid(self, form):
        response = super().form_valid(form)
        objet = getattr(self, "object", None) or getattr(form, "instance", None)
        if objet is not None:
            try:
                modifications = diff(self._audit_before or {}, self.audit_snapshot(objet))
            except Exception:  # noqa: BLE001
                audit_logger.exception("audit : diff impossible sur %r", objet)
                modifications = {}
            audit_emit_changes(
                objet, modifications, self.request,
                permission_fields=self.audit_permission_fields,
                status_fields=self.audit_status_fields,
            )
        return response


class AuditDeleteMixin(AuditedViewMixin):
    """
    Journalise une SUPPRESSION AVANT que l'objet ne disparaisse : `log_delete()`
    fige le libellé de l'objet et l'intégralité de ses valeurs dans
    `extra["valeurs"]`, ce qui garde le journal lisible après coup.
    """

    def form_valid(self, form):
        objet = getattr(self, "object", None)
        if objet is None:
            try:
                objet = self.get_object()
            except Exception:  # noqa: BLE001
                objet = None
        if objet is not None:
            contexte = {}
            for nom, labeller in (self.audit_m2m_fields or {}).items():
                contexte[nom] = audit_m2m_labels(objet, nom, labeller)
            log_delete(objet, request=self.request, extra=contexte or None)
        return super().form_valid(form)


# --- Clients : un client = un ClientProfile + un compte User ----------------
# Les deux objets sont créés, modifiés et supprimés ensemble par le back-office.
# Le journal doit donc refléter les DEUX, sinon la trace est incomplète.

# Champs du compte utilisateur repris dans la photo d'un client.
AUDIT_CLIENT_ACCOUNT_FIELDS = ("email", "username", "first_name", "last_name", "is_active")


def audit_client_snapshot(profil):
    """Photo d'un client : son profil + les champs utiles de son compte."""
    etat = audit_snapshot(profil)
    try:
        compte = profil.user
        for nom in AUDIT_CLIENT_ACCOUNT_FIELDS:
            etat[f"compte_{nom}"] = getattr(compte, nom, None)
    except Exception:  # noqa: BLE001
        audit_logger.debug("audit : compte du client illisible", exc_info=True)
    return etat


def audit_client_created(user, request):
    """Journalise la création d'un client (profil + compte de connexion)."""
    try:
        profil = getattr(user, "client_profile", None)
    except Exception:  # noqa: BLE001
        profil = None
    cible = profil if profil is not None else user
    log_create(cible, request=request, extra={
        "valeurs": audit_client_snapshot(profil) if profil is not None else audit_snapshot(user),
        "compte_utilisateur_cree": str(user),
    })


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
    """Déconnexion (back-office ou site) → formulaire de connexion unique.

    Sécurité : seule une requête POST (donc protégée par le jeton CSRF via
    CsrfViewMiddleware) déconnecte réellement. En GET, on ne fait que rediriger.
    Sans cela, un simple lien suffit à déconnecter : préchargement du navigateur,
    extension, ou balise ``<img src="/gestion/deconnexion/">`` hébergée sur un
    site tiers. C'est exactement la raison pour laquelle Django impose le POST
    sur ``LogoutView`` depuis la version 5.

    Choix pour le cas GET : redirection douce plutôt qu'un 405. Un utilisateur
    ayant gardé l'ancienne URL en favori (ou un lien envoyé par mail) atterrit
    sur une page utile au lieu d'une page d'erreur, et surtout sa session reste
    intacte — c'est le point important.
    """
    if request.method != "POST":
        if request.user.is_authenticated:
            # Retour à l'espace correspondant au profil de l'utilisateur.
            return redirect("gestion:index" if request.user.is_staff else "front:index")
        return redirect("front:login")

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


class ProductCreateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                        AuditCreateMixin, CreateView):
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


class ProductUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                        AuditUpdateMixin, UpdateView):
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


class ProductDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                        AuditDeleteMixin, DeleteView):
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
                stock_avant = self._product.quantity
                movement = StockService.apply_movement(product_id, movement_type, quantity, note, request.user)
                self._audit_movement(movement, stock_avant)
                messages.success(request, "Mouvement enregistré.")
                return redirect("gestion:product-list")
        except ValueError as e:
            messages.error(request, str(e))
        return super().get(request, *args, **kwargs)

    def _audit_movement(self, movement, stock_avant):
        """
        Journalise le mouvement de stock : type (entrée/sortie), quantité,
        motif, et effet sur le stock du produit.
        Protégé : un journal en panne ne doit pas annuler le mouvement.
        """
        try:
            produit = Product.objects.filter(pk=movement.product_id).first()
            log_action(
                AuditLog.Action.CREATE,
                request=self.request,
                obj=movement,
                changes={"stock_produit": {
                    "avant": stock_avant,
                    "apres": produit.quantity if produit else None,
                }},
                extra={
                    "produit": str(produit) if produit else str(movement.product_id),
                    "type_mouvement": movement.get_movement_type_display(),
                    "quantite": movement.quantity,
                    "motif": movement.note or "",
                },
            )
        except Exception:  # noqa: BLE001
            audit_logger.exception("audit : mouvement de stock non journalisé")

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
        user = form.save()
        audit_client_created(user, self.request)
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
        # Photo AVANT enregistrement : `form` porte sa propre instance de profil,
        # celle-ci en est une copie fraîche, non touchée par form.save().
        avant = audit_client_snapshot(self.get_object())
        form.save()
        self._audit_update(form, avant)
        messages.success(self.request, "Client mis à jour.")
        return redirect(self.success_url)

    def _audit_update(self, form, avant):
        """
        Journalise la modification du client. La réinitialisation du mot de
        passe est tracée comme un FAIT : on teste seulement la présence d'une
        valeur, jamais son contenu.

        Le fait est porté par la VALEUR de la clé « evenement » et non par un
        nom de clé : `services.to_jsonable()` masque toute clé contenant
        « mot_de_passe », y compris un innocent « mot_de_passe_modifie ».
        """
        try:
            profil = form.client_profile
            modifications = diff(avant, audit_client_snapshot(profil))
            contexte = {}
            if form.cleaned_data.get("password1"):
                contexte["evenement"] = "Mot de passe réinitialisé par l'administrateur"
            if not modifications and not contexte:
                return
            log_action(
                AuditLog.Action.UPDATE,
                request=self.request,
                obj=profil,
                changes=modifications,
                extra=contexte or None,
            )
        except Exception:  # noqa: BLE001
            audit_logger.exception("audit : modification de client non journalisée")


class ClientDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DeleteView):
    permission_required = "clients.delete_clientprofile"
    model = ClientProfile
    template_name = "admin/gestion/client_confirm_delete.html"
    context_object_name = "client"
    success_url = reverse_lazy("gestion:client-list")

    def form_valid(self, form):
        obj = self.get_object()
        user = obj.user
        # Journalisation AVANT les deux suppressions : ensuite, ni le profil ni
        # le compte n'existent plus et leurs libellés seraient perdus.
        log_delete(obj, request=self.request, extra={
            "compte_utilisateur_supprime": str(user),
            "email": getattr(user, "email", ""),
        })
        log_delete(user, request=self.request, extra={
            "motif": "Suppression du client depuis le back-office",
            "profil_client_supprime": str(obj),
        })
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
        statut_avant = quote.status
        quote.status = QuoteRequest.Status.PROCESSED
        quote.save(update_fields=["status", "updated_at"])
        if statut_avant != quote.status:
            audit_emit_changes(
                quote,
                {"status": {"avant": statut_avant, "apres": quote.status}},
                request,
                status_fields=("status",),
            )
        messages.success(request, f"La demande a été marquée comme traitée.")
        return redirect("gestion:quote-list")


class QuoteRequestUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                             AuditUpdateMixin, UpdateView):
    """Modification du statut et des notes admin d'une demande de devis."""
    permission_required = "quotes.change_quoterequest"
    model = QuoteRequest
    template_name = "admin/gestion/quote_form.html"
    context_object_name = "quote"
    fields = ("status", "admin_notes")
    success_url = reverse_lazy("gestion:quote-list")
    # Un changement de statut est journalisé comme STATUS_CHANGE ; les notes
    # admin restent un UPDATE classique.
    audit_status_fields = ("status",)

    def form_valid(self, form):
        messages.success(self.request, "La demande de devis a été mise à jour.")
        return super().form_valid(form)


class QuoteRequestDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                             AuditDeleteMixin, DeleteView):
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
            avant = capture(request.user)  # photo AVANT le save du formulaire
            form.save()
            log_update(request.user, avant, request=request)
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
        response = super().form_valid(form)
        # On journalise le FAIT, jamais la valeur : ni l'ancien ni le nouveau
        # mot de passe ne sont lus dans form.cleaned_data.
        log_action(
            AuditLog.Action.UPDATE,
            request=self.request,
            obj=self.request.user,
            extra={"evenement": "Changement de mot de passe"},
        )
        return response


# ——— Utilisateurs (permissions « personnel ») ———

def staff_queryset_visible_to(user):
    """
    Personnel visible par `user`.

    Les comptes Super Administrateur sont réservés aux superusers : un Administrateur
    ne peut ni les lister, ni les ouvrir par URL, ni les modifier ou les supprimer.
    """
    qs = User.objects.filter(is_staff=True)
    if not user.is_superuser:
        qs = qs.exclude(is_superuser=True)
    return qs


class UserListView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, ListView):
    """Liste du personnel (utilisateurs back-office). Les clients sont gérés dans Catalogue > Clients."""
    model = User
    permission_required = "accounts.view_user"
    template_name = "admin/gestion/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        return staff_queryset_visible_to(self.request.user).order_by("email").prefetch_related("groups")


class UserCreateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditCreateMixin, CreateView):
    """Création d'un utilisateur (connexion par email)."""
    model = User
    permission_required = "accounts.add_user"
    form_class = UserCreateForm
    template_name = "admin/gestion/user_form.html"
    success_url = reverse_lazy("gestion:user-list")
    # Les rôles attribués à la création sont journalisés par leur NOM.
    audit_m2m_fields = {"groups": None}

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


class UserUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditUpdateMixin, UpdateView):
    """Édition d'un utilisateur."""
    model = User
    permission_required = "accounts.change_user"
    form_class = UserUpdateForm
    template_name = "admin/gestion/user_form.html"
    context_object_name = "user_obj"
    success_url = reverse_lazy("gestion:user-list")
    # Rôles photographiés par leur NOM (« Vendeur »), pas par leur identifiant.
    audit_m2m_fields = {"groups": None}
    # Les modifications les plus sensibles de l'application : elles sortent du
    # simple UPDATE et deviennent un PERMISSION_CHANGE.
    audit_permission_fields = ("groups", "is_staff", "is_active", "is_superuser")

    def get_queryset(self):
        return staff_queryset_visible_to(self.request.user)

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


class UserDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditDeleteMixin, DeleteView):
    """Suppression d'un utilisateur."""
    model = User
    permission_required = "accounts.delete_user"
    template_name = "admin/gestion/user_confirm_delete.html"
    context_object_name = "user_obj"
    success_url = reverse_lazy("gestion:user-list")
    audit_m2m_fields = {"groups": None}

    def get_queryset(self):
        return staff_queryset_visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Utilisateur supprimé.")
        return super().form_valid(form)


# ——— Rôles (Group, permissions « rôles ») ———

class RoleListView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, ListView):
    """Liste des rôles (groupes Django)."""
    model = Group
    permission_required = "auth.view_group"
    template_name = "admin/gestion/role_list.html"
    context_object_name = "roles"
    paginate_by = 20

    def get_queryset(self):
        return Group.objects.prefetch_related("permissions").order_by("name")


class RoleDetailView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin, DetailView):
    """Détail d'un rôle : permissions attribuées et personnel avec ce rôle."""
    model = Group
    permission_required = "auth.view_group"
    template_name = "admin/gestion/role_detail.html"
    context_object_name = "role"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .forms import get_permission_label, get_permission_section
        role_perms = self.object.permissions.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        grouped = {}
        for p in role_perms:
            grouped.setdefault(get_permission_section(p), []).append(get_permission_label(p))
        context["permissions_grouped"] = list(grouped.items())
        context["users_with_role"] = self.object.user_set.filter(is_staff=True).order_by("email")
        return context


class RoleCreateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditCreateMixin, CreateView):
    """Création d'un rôle."""
    model = Group
    permission_required = "auth.add_group"
    form_class = GroupForm
    template_name = "admin/gestion/role_form.html"
    success_url = reverse_lazy("gestion:role-list")
    # Permissions journalisées avec leur libellé métier (« Voir les produits »).
    audit_m2m_fields = {"permissions": audit_permission_labels}

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


class RoleUpdateView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditUpdateMixin, UpdateView):
    """Édition d'un rôle."""
    model = Group
    permission_required = "auth.change_group"
    form_class = GroupForm
    template_name = "admin/gestion/role_form.html"
    context_object_name = "role"
    success_url = reverse_lazy("gestion:role-list")
    audit_m2m_fields = {"permissions": audit_permission_labels}
    # Modifier les permissions d'un rôle, c'est modifier les droits de tous
    # ceux qui le portent → PERMISSION_CHANGE, avec le détail avant/après.
    audit_permission_fields = ("permissions",)

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


class RoleDeleteView(StaffRequiredMixin, PermissionRequiredMixin, GestionLayoutMixin,
                     AuditDeleteMixin, DeleteView):
    """Suppression d'un rôle."""
    model = Group
    permission_required = "auth.delete_group"
    template_name = "admin/gestion/role_confirm_delete.html"
    context_object_name = "role"
    success_url = reverse_lazy("gestion:role-list")
    audit_m2m_fields = {"permissions": audit_permission_labels}

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
